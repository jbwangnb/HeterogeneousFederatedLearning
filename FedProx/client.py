import json
from copy import deepcopy
from random import randrange

import numpy as np
from torch.utils.data import DataLoader, sampler, Subset
import torch

import datasets
from FedProx import models
from server import Server


class Client(object):

    def __init__(self, conf, model, train_dataset, non_iid, id=-1):
        self.client_id = id

        self.conf = conf
        # 客户端本地模型(一般由服务器传输)
        self.local_model = models.get_model(self.conf["model_name"])
        self.local_model.load_state_dict(model.state_dict())

        sub_trainset: Subset = Subset(train_dataset, indices=non_iid)
        self.train_loader = DataLoader(sub_trainset, batch_size=conf["batch_size"], shuffle=False)

    def local_train(self, global_model):
        for name, param in global_model.state_dict().items():
            self.local_model.state_dict()[name].copy_(param.clone())
        optimizer = torch.optim.SGD(self.local_model.parameters(), lr=self.conf['lr'], momentum=self.conf['momentum'])
        self.local_model.train()
        for e in range(self.conf["local_epochs"]):
            for batch_id, batch in enumerate(self.train_loader):
                data, target = batch
                if torch.cuda.is_available():
                    data = data.cuda()
                    target = target.cuda()

                optimizer.zero_grad()
                output = self.local_model(data)

                if len(target) == 1:
                    _output = torch.zeros(1, len(output))
                    output = _output
                # FedProx的loss函数,计算 proximal_term
                proximal_term = 0.0
                for w, w_t in zip(self.local_model.parameters(), global_model.parameters()):
                    proximal_term += (w - w_t).norm(2)
                loss = torch.nn.functional.cross_entropy(output, target) + \
                       (self.conf["mu"] / 2) * proximal_term

                loss.backward()
                optimizer.step()

            print("Client {} Epoch {} done.".format(self.client_id, e))

        diff = dict()
        for name, data in self.local_model.state_dict().items():
            diff[name] = (data - global_model.state_dict()[name])
        return diff
