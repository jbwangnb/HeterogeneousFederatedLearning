import numpy as np
from torch.utils.data import DataLoader, sampler, Subset
import torch

import models


class Client(object):

    def __init__(self, conf, model, train_dataset, eval_dataset, non_iid, id=-1):
        self.client_id = id

        self.conf = conf
        self.local_model = models.get_model(self.conf["model_name"])
        self.local_model.load_state_dict(model.state_dict())

        sub_trainset: Subset = Subset(train_dataset, indices=non_iid)

        self.train_loader = DataLoader(sub_trainset, batch_size=conf["batch_size"], shuffle=False)
        self.eval_loader = DataLoader(eval_dataset, batch_size=self.conf["batch_size"], shuffle=True)

    def update_model(self, global_model):
        for name, param in global_model.state_dict().items():
            if 'bn' not in name:
                self.local_model.state_dict()[name].copy_(param.clone())

    def local_train(self, global_model):

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
                loss = torch.nn.functional.cross_entropy(output, target)
                loss.backward()
                optimizer.step()

            print("Client {} Epoch {} done.".format(self.client_id, e))

        diff = dict()
        for name, data in self.local_model.state_dict().items():
            diff[name] = (data - global_model.state_dict()[name])
        return diff

    def model_eval(self):
        self.local_model.eval()
        total_loss = 0.0
        correct = 0
        dataset_size = 0
        for batch_id, batch in enumerate(self.eval_loader):
            data, target = batch
            dataset_size += data.size()[0]

            if torch.cuda.is_available():
                data = data.cuda()
                target = target.cuda()

            output = self.local_model(data)

            total_loss += torch.nn.functional.cross_entropy(output, target, reduction='sum').item()
            pred = output.data.max(1)[1]
            correct += pred.eq(target.data.view_as(pred)).cpu().sum().item()

        acc = 100.0 * (float(correct) / float(dataset_size))
        total_l = total_loss / dataset_size

        return acc, total_l


if __name__ == '__main__':
    print(np.random.dirichlet(alpha=1, size=3))
