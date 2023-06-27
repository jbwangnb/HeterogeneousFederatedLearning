import copy
from torch.utils.data import DataLoader, sampler
import torch
import models


class Client(object):

    def __init__(self, conf, model, train_dataset, non_iid, id=-1):
        self.client_id = id

        self.conf = conf
        # 客户端本地模型(一般由服务器传输)
        self.local_model = models.get_model(self.conf["model_name"])
        self.control_local = models.get_model(self.conf["model_name"])
        self.local_model.load_state_dict(model.state_dict())
        for name, data in self.control_local.state_dict().items():
            data.add_(-data)

        self.train_dataset = train_dataset

        self.non_iid = non_iid

        # 按ID对训练集合的拆分

        self.train_loader = DataLoader(self.train_dataset, batch_size=conf["batch_size"], shuffle=True)

    def local_train(self, global_model, control_global):

        global_weights = global_model.state_dict()
        for name, param in global_model.state_dict().items():
            self.local_model.state_dict()[name].copy_(param.clone())
        optimizer = torch.optim.SGD(self.local_model.parameters(), lr=self.conf['lr'], momentum=self.conf['momentum'])
        self.local_model.train()

        control_global_w = control_global.state_dict()
        control_local_w = self.control_local.state_dict()

        count = 0
        for e in range(self.conf["local_epochs"]):
            _data = torch.zeros(self.conf["batch_size"], self.conf["channels"], self.conf["pic_size"],
                                self.conf["pic_size"])
            _target = torch.zeros(self.conf["batch_size"], dtype=torch.long)
            index = 0
            for batch_id, batch in enumerate(self.train_loader):
                data, target = batch
                # non-iid data
                for i in range(len(target)):
                    if int(target[i]) in self.non_iid:
                        _target[index] = target[i]
                        _data[index] = data[i]
                        index += 1
                        if index == self.conf["batch_size"]:
                            index = 0
                            if torch.cuda.is_available():
                                _data = _data.cuda()
                                _target = _target.cuda()
                            optimizer.zero_grad()
                            output = self.local_model(_data)
                            loss = torch.nn.functional.cross_entropy(output, _target)
                            loss.backward()
                            optimizer.step()

                            local_weights = self.local_model.state_dict()
                            for w in local_weights:
                                # 根据控制变量进行再一次的梯度更新
                                local_weights[w] = local_weights[w] - self.conf["lr"] * (control_global_w[w] - control_local_w[w])
                            # 更新本地模型参数
                            self.local_model.load_state_dict(local_weights)
                            # 客户机所有局部训练完成后，一共经过了多少批次的训练
                            count += 1

            print("Client {} Epoch {} done.".format(self.client_id, e))

        new_control_local_w = self.control_local.state_dict()
        control_delta = copy.deepcopy(control_local_w)
        model_weights = self.local_model.state_dict()
        local_delta = copy.deepcopy(model_weights)
        for w in model_weights:
            # 更新局部控制变量
            new_control_local_w[w] = new_control_local_w[w] - control_global_w[w] + (
                    global_weights[w] - model_weights[w]) / (count * self.conf["lr"])
            # 计算局部控制变量的变化差值，用于更新全局控制变量
            control_delta[w] = new_control_local_w[w] - control_local_w[w]
            # 计算模型参数与上一轮全局模型参数的差值，用于更新全局模型参数
            local_delta[w] -= global_weights[w]

        self.control_local.load_state_dict(new_control_local_w)

        return self.local_model.state_dict(), control_delta, local_delta
