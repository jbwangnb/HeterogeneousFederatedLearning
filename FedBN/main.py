﻿import copy
import json

from server import Server
from client import *
import datasets

if __name__ == '__main__':

    with open("../utils/conf.json", 'r') as f:
        conf = json.load(f)

    train_datasets, eval_datasets = datasets.get_dataset("../data/", conf["type"])

    server = Server(conf, eval_datasets)

    clients = []

    # non-IID数据
    client_idx = datasets.get_nonIID_data(conf)

    # print(client_idx)

    for c in range(conf["clients"]):
        clients.append(Client(conf, server.global_model, train_datasets, eval_datasets, client_idx[c + 1], c + 1))

    all_acc = {}
    for e in range(conf["global_epochs"]):
        print("Global Epoch %d" % e)
        candidates = clients

        weight_accumulator = {}
        for name, params in server.global_model.state_dict().items():
            weight_accumulator[name] = torch.zeros_like(params)

        for c in candidates:

            diff = c.local_train(server.global_model)

            for name, params in server.global_model.state_dict().items():
                weight_accumulator[name].add_(diff[name])

        server.model_aggregate(weight_accumulator)

        for c in candidates:
            c.update_model(server.global_model)
            acc, loss = c.model_eval()
            print("Client %d, Global Epoch %d, acc: %f, loss: %f" % (c.client_id, e, acc, loss))

            if c.client_id in list(all_acc.keys()):
                all_acc[c.client_id].append(acc)
            else:
                all_acc[c.client_id] = [acc]

        # acc, loss = server.model_eval()
        # all_acc.append(acc)
        # print("Global Epoch %d, acc: %f, loss: %f" % (e, acc, loss))

    print(all_acc)
