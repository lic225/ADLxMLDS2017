import torch
import torch.nn as nn
from torch.autograd import Variable
import argparse
import glob
from util import *
from timit import *
import random
import numpy as np
import model_rnn
import model_cnn
import model_brnn
import model_bcnn
import model_res
import model_bres

parser = argparse.ArgumentParser(description='')
parser.add_argument('data', default='./data/',
                    help='data folder')
parser.add_argument('feat', default='mfcc',
                    help='mfcc or fbank or all')
parser.add_argument('model', default='rnn',
                    help='model (rnn or cnn or brnn or bcnn or res or bres)')
parser.add_argument('-l', '--lr', type=float, default=float(0.1))
parser.add_argument('-e', '--n_epoch', type=int, default=int(3))
parser.add_argument('-wx', '--window_size_x', type=int, default=int(3))
parser.add_argument('-wy', '--window_size_y', type=int, default=int(2))
parser.add_argument('-p', '--pool_size', type=int, default=int(2))
parser.add_argument('-H', '--hidden_size', type=int, default=int(20))
parser.add_argument('-b', '--batch_size', type=int, default=int(32))
parser.add_argument('-n', '--n_layers', type=int, default=int(1))
parser.add_argument('-d', '--dropout', type=float, default=int(0.0))
parser.add_argument('-M', '--Model', type=str, default='')

args = parser.parse_args()


LR = args.lr
N_EPOCH = args.n_epoch
HIDDEN_SIZE = args.hidden_size
POOL_SIZE = args.pool_size
WINDOW_SIZE = (args.window_size_x, args.window_size_y)
BATCH_SIZE = args.batch_size
N_LAYERS = args.n_layers
DROPOUT = args.dropout

print_every = 10
plot_every = 10

print(args.model, args.feat, LR, N_EPOCH, HIDDEN_SIZE, N_LAYERS, BATCH_SIZE, WINDOW_SIZE, DROPOUT)

timit = TIMIT(args.data, "tr", args.feat)

if args.model == "rnn":
    model = model_rnn.RNN(timit.N_FEAT, HIDDEN_SIZE, timit.N_LABEL, BATCH_SIZE, N_LAYERS, DROPOUT)
elif args.model == "brnn":
    model = model_brnn.BRNN(timit.N_FEAT, HIDDEN_SIZE, timit.N_LABEL, BATCH_SIZE, N_LAYERS, DROPOUT)
elif args.model == "cnn":
    model = model_cnn.CNN(timit.N_FEAT, WINDOW_SIZE, POOL_SIZE, HIDDEN_SIZE, timit.N_LABEL, BATCH_SIZE, N_LAYERS, DROPOUT)
elif args.model == "bcnn":
    model = model_bcnn.BCNN(timit.N_FEAT, WINDOW_SIZE, POOL_SIZE, HIDDEN_SIZE, timit.N_LABEL, BATCH_SIZE, N_LAYERS, DROPOUT)
elif args.model == "res":
    model = model_res.RESR(timit.N_FEAT, HIDDEN_SIZE, timit.N_LABEL, BATCH_SIZE, N_LAYERS, DROPOUT)
elif args.model == "bres":
    model = model_bres.BRESR(timit.N_FEAT, HIDDEN_SIZE, timit.N_LABEL, BATCH_SIZE, N_LAYERS, DROPOUT)

if USE_CUDA:
    model.cuda()

if args.Model != '':
    print("warm start: ", args.Model)
    state_dict = torch.load(os.path.join("models", args.Model), map_location=lambda storage, location: storage)
    model.load_state_dict(state_dict)

opt = torch.optim.Adam(model.parameters(), lr = LR)
criterion = nn.CrossEntropyLoss(timit.label_wt())

cnt = 0

def batch_eval(inp, target, ids, useful, lens):
    # inp: (BATCH_SIZE x maxlen x N_FEAT)
    # target: (BATCH_SIZE x maxlen)
    hidden = model.init_hidden()
    output, hidden = model(inp, hidden, lens)

    acc = 0
    loss = 0

    for i in range(useful):
        loss += criterion(output[i][:lens[i]], target[i][:lens[i]]).data[0] * lens[i]
        my_y = output[i].max(1)[1].data[:lens[i]]
        ta_y = target[i].data[:lens[i]]
        acc += sum(ta_y == my_y)

#        if i == 0:
#            print(ids[i])
#            print(list(my_y[:40]))
#            print(list(my_y[-40:]))
#            print(list(ta_y[:40]))
#            print(list(ta_y[-40:]))

    return loss, acc


def eval_valid(epoch):
    loss = 0
    acc = 0
    v_len = len(timit.valid_set)
    random.shuffle(timit.valid_set)
    tot_len = 0
    model.eval()
    for i in range(0, v_len, BATCH_SIZE):
        input, target, ids, useful = timit.get_batch(i, BATCH_SIZE, "va")
        input, target, ids, lens = make_batch(input, target, ids, timit.N_FEAT)
        tloss, tacc = batch_eval(input, target, ids, useful, lens)
        loss += tloss
        acc  += tacc
        tot_len += sum(lens[:useful])

    loss /= tot_len
    acc /= tot_len
    # acc /= v_len

    print("  epoch %d VALID LOSS %f ACC %f%%" % (epoch, loss, acc * 100))

    return loss, acc


eval_valid(0)
iter = 1
start = time.time()
for epoch in range(1, N_EPOCH + 1):
    loss_tot = 0
    random.shuffle(timit.tr_set)
    model.train()
    for i in range(0, len(timit.tr_set), BATCH_SIZE):
        input, target, ids, useful = timit.get_batch(i, BATCH_SIZE)

        input, target, ids, lens = make_batch(input, target, ids, timit.N_FEAT)

        model.zero_grad()
        hidden = model.init_hidden()
        output, hidden = model(input, hidden, lens)

        loss = 0
        for j in range(useful):
            loss += criterion(output[j][:lens[j]], target[j][:lens[j]])

        if USE_CUDA:
            loss.cuda()

        loss.backward()
        opt.step()

        loss = loss.data[0] / useful

        loss_tot += loss

        if iter % print_every == 0:
#            print(ids[0])
#            print(list(output[0].data.max(1)[1][:40]))
#            print(list(output[0].data.max(1)[1][-40:]))
#            print(list(target[0].data[:40]))
#            print(list(target[0].data[-40:]))
            print('[%s (%d %d%%) %.4f %.4f]' %
                  (time_since(start),
                   iter,
                   iter / (N_EPOCH * len(timit.tr_set)) * 100,
                   loss,
                   loss_tot / (i//BATCH_SIZE+1)))

        iter += 1

    eval_valid(epoch)
    model_name = args.model

    if args.model == "cnn":
        model_name += (".%s.e%d.h%d.b%d.l%d.wx%d.wy%d.p%d.pt" % (
            args.feat, epoch, HIDDEN_SIZE, BATCH_SIZE, N_LAYERS, WINDOW_SIZE[0], WINDOW_SIZE[1], POOL_SIZE))
    else:
        model_name += (".%s.e%d.h%d.b%d.l%d.d%g.pt" % (
            args.feat, epoch, HIDDEN_SIZE, BATCH_SIZE, N_LAYERS, DROPOUT))

    torch.save(model.state_dict(), os.path.join("models", model_name))
