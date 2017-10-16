import torch
import torch.nn as nn
from torch.autograd import Variable
import argparse
import glob
from util import *
from timit import *
import random
import model_rnn
import model_cnn
import model_brnn
import model_dnn

parser = argparse.ArgumentParser(description='')
parser.add_argument('data', default='./data/',
                    help='data folder')
parser.add_argument('feat', default='mfcc',
                    help='mfcc or fbank')
parser.add_argument('model', default='rnn',
                    help='model (rnn or cnn or brnn or dnn)')
parser.add_argument('-l', '--lr', type=float, default=float(0.1))
parser.add_argument('-e', '--n_epoch', type=int, default=int(3))
parser.add_argument('-wx', '--window_size_x', type=int, default=int(3))
parser.add_argument('-wy', '--window_size_y', type=int, default=int(2))
parser.add_argument('-p', '--pool_size', type=int, default=int(2))
parser.add_argument('-H', '--hidden_size', type=int, default=int(20))
parser.add_argument('-b', '--batch_size', type=int, default=int(32))
parser.add_argument('-n', '--n_layers', type=int, default=int(1))
parser.add_argument('-d', '--dropout', type=float, default=int(0.0))

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
elif args.model == "cnn":
    model = model_cnn.CNN(timit.N_FEAT, WINDOW_SIZE, POOL_SIZE, HIDDEN_SIZE, timit.N_LABEL, BATCH_SIZE, N_LAYERS, DROPOUT)
elif args.model == "brnn":
    model = model_brnn.BRNN(timit.N_FEAT, HIDDEN_SIZE, timit.N_LABEL, BATCH_SIZE, N_LAYERS, DROPOUT)
elif args.model == "dnn":
    model = model_dnn.DNN(timit.N_FEAT, HIDDEN_SIZE, timit.N_LABEL, BATCH_SIZE, N_LAYERS, DROPOUT)

if USE_CUDA:
    model.cuda()

opt = torch.optim.Adam(model.parameters(), lr = LR)
criterion = nn.CrossEntropyLoss(timit.label_wt())
# criterion = nn.CrossEntropyLoss()

cnt = 0

def train(inp, target, useful, lens):
    # inp: (BATCH_SIZE x maxlen x N_FEAT)
    # target: (BATCH_SIZE x maxlen)
    global cnt
    model.train()
    hidden = model.init_hidden()
    model.zero_grad()
    output, hidden = model(inp, hidden, lens)

    loss = 0
    for i in range(useful):
        loss += criterion(output[i][:lens[i]], target[i][:lens[i]])

#    loss = criterion(output.view(-1, timit.N_LABEL), target.view(-1))
    if USE_CUDA:
        loss.cuda()

    loss.backward()
    opt.step()

#    if cnt % print_every == 0:
#        print(lens[5])
#        print(list(output[5].max(1)[1].data[:lens[5]]))
#        print(list(target[5].data[:lens[5]]))
    cnt += 1

    return loss.data[0] / useful


def batch_eval(inp, target, useful, lens):
    # inp: (BATCH_SIZE x maxlen x N_FEAT)
    # target: (BATCH_SIZE x maxlen)
    hidden = model.init_hidden()
    output, hidden = model(inp, hidden, lens)

    acc = 0
    loss = 0

    for i in range(useful):
        loss += criterion(output[i][:lens[i]], target[i][:lens[i]]).data[0] * lens[i]
        my_y = output[i].max(1)[1]
        ta_y = target[i]
        acc += sum(my_y[:lens[i]] == ta_y[:lens[i]]).data[0]

    return loss, acc


def eval_valid(epoch):
    loss = 0
    acc = 0
    v_len = len(timit.valid_set)
    tot_len = 0
    model.eval()
    for i in range(0, v_len, BATCH_SIZE):
        input, target, useful = timit.get_batch(i, BATCH_SIZE, "va")
        input, target, lens = make_batch(input, target, timit.N_FEAT)
        tloss, tacc = batch_eval(input, target, useful, lens)
        loss += tloss
        acc  += tacc
        tot_len += sum(lens[:useful])

    loss /= tot_len
    acc /= tot_len

    print("  epoch %d VALID LOSS %f ACC %f%%" % (epoch, loss, acc * 100))

    return loss, acc


start = time.time()
loss_avg = 0
all_losses = []
loss_tot = 0

iter = 1
eval_valid(0)
for epoch in range(1, N_EPOCH + 1):
    random.shuffle(timit.tr_set)
    for i in range(0, len(timit.tr_set), BATCH_SIZE):
    # for i in range(0, 100, BATCH_SIZE):
        input, target, useful = timit.get_batch(i, BATCH_SIZE)

        input, target, lens = make_batch(input, target, timit.N_FEAT)

        loss = train(input, target, useful, lens)

        loss_avg += loss
        loss_tot += loss

        if iter % print_every == 0:
            print('[%s (%d %d%%) %.4f %.4f]' %
                  (time_since(start), iter, iter / (N_EPOCH * len(timit.tr_set)) * 100, loss, loss_tot / iter))

        if iter % plot_every == 0:
            all_losses.append(loss_avg / plot_every)
            loss_avg = 0

        iter += 1
    eval_valid(epoch)
    torch.save(
        model.state_dict(),
        os.path.join("models", 
        args.model + ("%s.e%d.h%d.b%d.l%d.pt" % (args.feat, epoch, HIDDEN_SIZE, BATCH_SIZE, N_LAYERS))))

print(all_losses)

