import numpy as np
from dataset_Reader import Variable_Spline_Dataset
from utils import progress_bar, init_params, my_print
import torch
import os
import torch.nn as nn
import torch.optim as optim
from torch.autograd import Variable
import torch.nn.functional as F
import torch.backends.cudnn as cudnn
import torchvision.transforms as transforms
from nn_model import ResNet34
from model import Multi_Point_Model, Multi_Point_Loss, Multi_Point_Scheduled_Sampling_Model
import config
import random
import sys
random.seed(config.manual_seed)
torch.manual_seed(config.manual_seed+1)

train_transform = transforms.Compose([
	transforms.ToTensor(),
	])

test_transform = transforms.Compose([
	transforms.ToTensor(),
	])

trainset = Variable_Spline_Dataset(path = config.dataset_path, n_all = config.n_data,
			train_part=config.train_part, train=True, transform=train_transform)
testset = Variable_Spline_Dataset(path = config.dataset_path, n_all = config.n_data,
			train_part=config.train_part, train=False, transform=test_transform)

trainloader = torch.utils.data.DataLoader(trainset, batch_size=config.train_batch_size,
			shuffle=True, num_workers=1)
testloader = torch.utils.data.DataLoader(testset, batch_size=config.test_batch_size,
			shuffle=False, num_workers=1)

if config.continue_train:
	print('Loading Model')
	net = torch.load(config.continue_model_name)['net']
else:
	net = Multi_Point_Scheduled_Sampling_Model()
	# net = ResNet34(config.n_point*config.n_dim)
	print(net)
	init_params(net)
	net.cuda()

criterion = Multi_Point_Loss()

optimizer = optim.Adam(net.parameters(), lr=config.lr, weight_decay=config.weight_decay)

def train(epoch):
	print('\nEpoch: %d' % epoch)
	net.train()
	train_loss = 0
	cul_mse_loss = 0
	cul_clf_loss = 0
	n_batch = 0
	for batch_idx, (inputs, labels, point_masks, clf_point) in enumerate(trainloader):
		inputs = inputs.float().cuda()
		labels = labels.float().cuda()
		point_masks = point_masks.float().cuda()
		clf_point = clf_point.long().cuda()
		inputs = Variable(inputs)
		labels = Variable(labels, requires_grad=False)
		point_masks = Variable(point_masks, requires_grad=False)
		clf_point = Variable(clf_point, requires_grad=False)
		optimizer.zero_grad()
		pred_pos, pred_prob = net(inputs, config.max_point, labels, clf_point)
		mse_loss, clf_loss = criterion(pred_pos, pred_prob, labels, point_masks, clf_point)
		loss = mse_loss + config.clf_weight*clf_loss
		loss.backward()
		optimizer.step()
		train_loss += loss.data[0]
		cul_mse_loss += mse_loss.data[0]
		cul_clf_loss += clf_loss.data[0]
		n_batch += 1
		progress_bar(batch_idx, len(trainloader), 'Loss: %.5f  %.5f %.5f %.5f %.5f %.5f'
			% (mse_loss.data[0], clf_loss.data[0], loss.data[0],
			   cul_mse_loss/(batch_idx+1), cul_clf_loss/(batch_idx+1), train_loss/(batch_idx+1)))
		# if config.debugging and (batch_idx+1)%config.debugging_iter == 0:
		# 	sys.exit(0)
	my_print('Epoch: %d Training: Loss: %.5f  %.5f %.5f'
			% (epoch, cul_mse_loss/n_batch, cul_clf_loss/n_batch, train_loss/n_batch))
	net.ss_prob += 0.1

def test(epoch):
	net.eval()
	test_predict = []
	test_label = []
	test_loss = 0.0
	cul_mse_loss = 0
	cul_clf_loss = 0
	loss = 0
	n_batch = 0

	for batch_idx, (inputs, labels, point_masks, clf_point) in enumerate(testloader):
		test_label.append(labels)
		inputs = inputs.float().cuda()
		labels = labels.float().cuda()
		point_masks = point_masks.float().cuda()
		clf_point = clf_point.long().cuda()
		inputs = Variable(inputs)
		labels = Variable(labels, requires_grad=False)
		point_masks = Variable(point_masks, requires_grad=False)
		clf_point = Variable(clf_point, requires_grad=False)

		pred_pos, pred_prob = net(inputs, config.max_point, labels, clf_point)
		test_predict.append((pred_pos.cpu().data, pred_prob.cpu().data))
		test_predict.append((pred_pos.cpu().data, pred_prob.cpu().data))
		mse_loss, clf_loss = criterion(pred_pos, pred_prob, labels, point_masks, clf_point)
		loss = mse_loss + config.clf_weight*clf_loss
		test_loss += loss.data[0]
		cul_mse_loss += mse_loss.data[0]
		cul_clf_loss += clf_loss.data[0]
		n_batch += 1
		progress_bar(batch_idx, len(testloader), 'Loss: %.5f %.5f %.5f %.5f %.5f %.5f'
		             % (mse_loss.data[0], clf_loss.data[0], loss.data[0],
		                cul_mse_loss / (batch_idx + 1), cul_clf_loss / (batch_idx + 1), test_loss/(batch_idx+1)))


	my_print('Epoch: %d Testing:Loss: %.5f  %.5f %.5f %.5f'
			% (epoch, cul_mse_loss/n_batch, cul_clf_loss/n_batch, loss.data[0], test_loss / n_batch))

	print('Saving..')
	state = {
		'net': net,
		'epoch': epoch,
	}
	if not os.path.isdir(config.checkpoint_path):
		os.makedirs(config.checkpoint_path)
	torch.save(state, os.path.join(config.checkpoint_path, 'chkt_%d'%(epoch)))
	score_state = {
		'test_predict': test_predict,
		'test_label': test_label,
	}
	test_predict = []
	test_label = []
	if not os.path.isdir(os.path.join(config.checkpoint_path, 'prediction')):
		os.makedirs(os.path.join(config.checkpoint_path, 'prediction'))
	torch.save(score_state, os.path.join(config.checkpoint_path, 'prediction/result_epoch_%d'%(epoch)))
	print('Saved at %s'%(config.checkpoint_path))




for epoch in range(1, config.max_epoch):
	train(epoch)
	test(epoch)
