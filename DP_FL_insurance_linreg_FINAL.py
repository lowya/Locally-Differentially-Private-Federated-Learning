#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""

@author: Andrew Lowy
"""
import numpy as np 
from numpy import mean
from numpy import median
from numpy import percentile
import pandas as pd
import matplotlib.pyplot as plt
import os
import sklearn
import statsmodels.api as sm
import statsmodels.formula.api as smf
import math
import scipy
import itertools
import json
from sklearn.model_selection import train_test_split


np.random.seed(2022)
#os.chdir('data')


 
df = pd.read_csv('insurance.csv')
#df.describe()
from sklearn.preprocessing import LabelEncoder
#sex
le = LabelEncoder()
le.fit(df.sex.drop_duplicates()) 
df.sex = le.transform(df.sex)
# smoker or not
le.fit(df.smoker.drop_duplicates()) 
df.smoker = le.transform(df.smoker)
#region
le.fit(df.region.drop_duplicates()) 
df.region = le.transform(df.region)


def clientsplit(N): #(almost) balanced split 
    dfs = [] #will store N dataframes (X_1, Y_1), ... (X_N, Y_N)
    n = int(np.ceil(len(df['charges'])/N))
    Ys = df['charges'].sort_values(ascending=True)
    indices = list(Ys.index)
    sorted_df = df.iloc[indices, ::]
    for i in range(N):
        dfs.append(sorted_df[i*n:(i+1)*n])
    return dfs
 
def feat_lab_by_mach(N): #returns 2 lists (each contains N dataframes): (non-standardized) features_by_machine, labels_by_machine
    features_by_machine = [] #just a helper fxn for splitdata - features are not standardized yet! 
    labels_by_machine = []
    dfs = clientsplit(N)
    for i in range(N):
        X = dfs[i].iloc[::, 0:6]
        X.insert(0, 'const', 1)
        Y = dfs[i].iloc[::, 6]
        features_by_machine.append(X)
        labels_by_machine.append(Y)
    return features_by_machine, labels_by_machine
    
    
def splitdata(N): #returns 4 arrays (each contains N dataframes): (standardized) train_features_by_machine, train_labels_by_machine, (standardized) test_... 
    train_features_by_machine = []
    train_labels_by_machine = []
    test_features_by_machine = []
    test_labels_by_machine = []
    features_by_machine, labels_by_machine = feat_lab_by_mach(N)
    for i in range(N):
        X, Y = feat_lab_by_mach(N)
        X_train, X_test, y_train, y_test = train_test_split(X[i], Y[i], test_size=0.20)
        standardized_Xtrain_cols = (X_train.iloc[::, 1:4:2] - X_train.iloc[::, 1:4:2].mean())/X_train.iloc[::, 1:4:2].std()
        standardized_Xtest_cols = (X_test.iloc[::, 1:4:2] - X_train.iloc[::, 1:4:2].mean())/X_train.iloc[::, 1:4:2].std()
        X_test = X_test.assign(age =standardized_Xtest_cols['age'])
        X_test = X_test.assign(bmi =standardized_Xtest_cols['bmi'])
        X_train = X_train.assign(age =standardized_Xtrain_cols['age'])
        X_train = X_train.assign(bmi =standardized_Xtrain_cols['bmi'])
        train_features_by_machine.append(X_train) 
        test_features_by_machine.append(X_test)
        train_labels_by_machine.append(y_train)
        test_labels_by_machine.append(y_test)
    return train_features_by_machine, train_labels_by_machine, test_features_by_machine, test_labels_by_machine 
    
    


################################################## Linear Regression ###############################################

#Preliminary functions:


def squared_loss_gradient(w, features, labels): #normalized by number of samples so it is the average batch gradient
    return -np.transpose(features)@(labels -features@w)/labels.shape[0]

def squared_loss_hessian(w,features,labels): #normalized by number of samples
    return np.transpose(features) @ features/labels.shape[0]

def F_eval(w, X, Y): #avg squared loss on input data set (or batch) X,Y #returns train or test RSS/n (= average train or test error)
    return (np.linalg.norm(Y - X@w)**2)/(2*Y.shape[0])

##################################################################################################################

def local_sgd_round(w_start, M, Mavail, K, stepsize, grad_eval, L):
    w_end = np.zeros_like(w_start) #initialize at 0
    #randomly choose Mavail out of the M clients:
    S = np.random.choice(list(range(M)), size=Mavail, replace=False, p=None)
    for m in S: #iterate through all Mavail available workers 
        w = w_start.copy()
        for _ in range(K): #K steps of local SGD 
            g = grad_eval(w, 1, m)
            c = min(1, L/np.linalg.norm(g)) #clip
            g = g*c
            w -= stepsize * g #one step 
        w_end += w / Mavail #average SGD updates across M clients  
    return w_end #return updated w


def noisy_local_sgd_round(w_start, M, Mavail, K, stepsize, grad_eval, L):
    w_end = np.zeros_like(w_start) #initialize at 0
    #randomly choose Mavail out of the M clients:
    S = np.random.choice(list(range(M)), size=Mavail, replace=False, p=None)
    for m in S: #iterate through all Mavail available workers 
        w = w_start.copy()
        for _ in range(K): #K steps of local SGD 
            g = grad_eval(w, 1, m)
            c = min(1, L/np.linalg.norm(g)) #clip
            g = g*c
            w -= stepsize * (g + gauss_AC(x_len, eps, delta, n, K*R, L, K)) #one step 
        w_end += w / Mavail #average SGD updates across M clients 
    return w_end #return updated w


def local_sgd(x_len, M, Mavail, K, R, stepsize, loss_freq, f_eval, grad_eval, L, avg_window=8):
    losses = []
    iterates = [np.zeros(x_len)] #initialize list with x_len 0's 
    for r in range(R):
        if len(iterates) >= avg_window: 
            iterates = iterates[-(avg_window-1):] #just store the last 8 iterates
        iterates.append(local_sgd_round(iterates[-1], M, Mavail, K, stepsize, grad_eval, L)) #run local sgd round and add it to iterates
        if (r+1) % loss_freq == 0:
            losses.append(f_eval(np.average(iterates,axis=0))) #evalute f (at average of last 8 iterates) every loss_freq rounds 
            print('Iteration: {:d}/{:d}   Loss: {:f}                 \r'.format(r+1,R,losses[-1]), end='')
            if losses[-1] > 5000000000:
                print('\nLoss is diverging: Loss = {:f}'.format(losses[-1]))
                return iterates, losses, 'diverged'
    print('')
    return iterates, losses, 'converged'


def minibatch_sgd(x_len, M, Mavail, K, R, stepsize, loss_freq, f_eval, grad_eval, L, avg_window=8):
    losses = []
    iterates = [np.zeros(x_len)]
    for r in range(R):
        if len(iterates) >= avg_window:
            iterates = iterates[-(avg_window-1):] #just store the last avg_window-1 =7 iterates
        g = np.zeros(x_len) #start with g = 0 vector of dim x_len = 100 
        #randomly choose Mavail out of the M clients:
        S = np.random.choice(list(range(M)), size=Mavail, replace=False, p=None)
        for m in S:
            c = min(1, L/np.linalg.norm(grad_eval(iterates[-1], K, m))) #clip (use bigger threshold since we are clipping sum of K grads)
            g += grad_eval(iterates[-1], K, m)*c #evaluate stoch MB grad of loss at last iterate and clip
        iterates.append(iterates[-1] - stepsize * g) #take SGD step and add new iterate to list iterates 
        if (r+1) % loss_freq == 0:
            losses.append(f_eval(np.average(iterates,axis=0))) #evalute f (at average of last 7 iterates) every loss_freq rounds and append to list "losses"
            print('Iteration: {:d}/{:d}   Loss: {:f}                 \r'.format(r+1,R,losses[-1]), end='')
            if losses[-1] > 5000000000:
                print('\nLoss is diverging: Loss = {:f}'.format(losses[-1]))
                return iterates, losses, 'diverged'
    print('')
    return iterates, losses, 'converged'   

def ACnoisyMB_sgd(eps, L, x_len, M, Mavail, K, R, stepsize, loss_freq, f_eval, grad_eval, avg_window=8):  
    losses = []
    iterates = [np.zeros(x_len)]
    for r in range(R):
        if len(iterates) >= avg_window:
            iterates = iterates[-(avg_window-1):] #just store the last avg_window-1 =7 iterates
        g = np.zeros(x_len) #start with g = 0 vector of dim x_len = 100 
        S = np.random.choice(list(range(M)), size=Mavail, replace=False, p=None)
        for m in S:
            n = len(train_labels_by_machine[m])
            delta = 1/n**2
            b = grad_eval(iterates[-1], K, m) 
            c = min(1, L/np.linalg.norm(b)) #clip
            b = b*c
            g = g + b + gauss_AC(x_len, eps, delta, n, R, L, K) 
        iterates.append(iterates[-1] - stepsize * g) #take SGD step and add new iterate to list iterates 
        if (r+1) % loss_freq == 0:
            losses.append(f_eval(np.average(iterates,axis=0)))
            #evalute F (at average of last 7 iterates) every loss_freq rounds and append to list "losses"
            print('Iteration: {:d}/{:d}   Loss: {:f}                 \r'.format(r+1,R,losses[-1]), end='')
            if losses[-1] > 5000000000:
                print('\nLoss is diverging: Loss = {:f}'.format(losses[-1]))
                return iterates, losses, 'diverged'
    print('')
    return iterates, losses, 'converged' #returns log loss fxn value 

def ACnoisy_local_sgd(eps, L, x_len, M, Mavail, K, R, stepsize, loss_freq, f_eval, grad_eval, avg_window=8): #LDP (not CDP) variant of McMahon et al 2018
    losses = []
    iterates = [np.zeros(x_len)] #initialize list with x_len 0's 
    for r in range(R):
        if len(iterates) >= avg_window: 
            iterates = iterates[-(avg_window-1):] #just store the last avg_window-1 =7 iterates
        iterates.append(noisy_local_sgd_round(iterates[-1], M, Mavail, K, stepsize, grad_eval, L)) #run local sgd round + noise, and add it to iterates
        if (r+1) % loss_freq == 0:
            losses.append(f_eval(np.average(iterates,axis=0))) #evalute F (at average of last 7 iterates) every loss_freq rounds 
            print('Iteration: {:d}/{:d}   Loss: {:f}                 \r'.format(r+1,R,losses[-1]), end='')
            if losses[-1] > 5000000000:
                print('\nLoss is diverging: Loss = {:f}'.format(losses[-1]))
                return iterates, losses, 'diverged'
    print('')
    return iterates, losses, 'converged'

    
#Newton used to compute minimizer w^* and f^*
def newtons_method(w_len, f_eval, grad_eval, hessian_eval, max_iter=1000, tol=1e-6):
    w = np.zeros(w_len)
    stepsize = 0.5
    for t in range(max_iter):
        gradient = grad_eval(w)
        hessian = hessian_eval(w)
        update_direction = np.linalg.solve(hessian, gradient)
        w -= stepsize * update_direction
        newtons_decrement = np.sqrt(np.dot(gradient, update_direction))
        if newtons_decrement <= tol:
            print("Newton's method converged after {:d} iterations".format(t+1))
            return f_eval(w), w
    print("Warning: Newton's method failed to converge")
    return f_eval(w), w


#def gauss_AC(d, eps, delta, n, R, L, K):
    #return np.random.multivariate_normal(mean = np.zeros(d), cov = (256*(L**2)*R*(np.log(2.5*R*K/(delta*n))*np.log(2/delta))/(n**2 * eps**2))*np.eye(d))
def gauss_AC(d, eps, delta, n, R, L, K): #moments account form of noise
    return np.random.multivariate_normal(mean = np.zeros(d), cov = (8*(L**2)*R*np.log(1/delta)/(n**2 * eps**2))*np.eye(d))


##############EXPERIMENTS###################
dim = 7
x_len = 7
DO_COMPUTE = True
###########YOU CAN SET THESE PARAMETERS#########: 
#N = 10, 5, 3, 15
#N = 3
N=10
M = N
#Mavail = 2
Mavail = 5
#R = 35, 50
R = 35
#K = 5
n = int(np.ceil(len(df['charges'])/N))
delta = 1/n**2
num_trials = 20
#num_trials = 1
loss_freq = 5
n_reps = 3
#n_reps = 2
n_stepsizes = 10
#n_stepsizes = 5
Ls = [100, 
      10000, 
      1000000, 
      100000000, 
      99999999999999999999999999999999]

# epsilons = [
#     .25, 
#     .5, 
#     1, 
#     2,
#     3.5, 
#     5]

epsilons = [
    .125,
    .25, 
    .5, 
    1, 
    2,
    3]

K = int(max(1, n*math.sqrt(max(epsilons)/(4*R)))) #needed for privacy by moments account; 
#K = int(max(1, n*max(epsilons)/(4*math.sqrt(2*R*math.log(2/delta))))) #needed for privacy by advanced comp; 


path = 'dp_insurance_N={:d}_M={:d}_K={:d}'.format(N,Mavail, K)



#########################
local_ls = np.zeros(num_trials)
MB_ls = np.zeros(num_trials)
noisylocal_ls = {}
noisyMB_ls = {}
noisyMB_tests_trials = {}
noisyloc_tests_trials = {}

noisyMB_NRMSE_trials = {}
noisyloc_NRMSE_trials = {}

for eps in epsilons:
    noisylocal_ls[eps] = np.ones(num_trials)*99999999999999999999999999999999
    noisyMB_ls[eps] = np.ones(num_trials)*99999999999999999999999999999999
    noisyMB_tests_trials[eps] = np.ones(num_trials)*99999999999999999999999999999999
    noisyloc_tests_trials[eps] = np.ones(num_trials)*99999999999999999999999999999999
    noisyMB_NRMSE_trials[eps] = np.ones(num_trials)*99999999999999999999999999999999
    noisyloc_NRMSE_trials[eps] = np.ones(num_trials)*99999999999999999999999999999999


upsilon = np.zeros(num_trials)

MB_tests_trials = np.zeros(num_trials)
loc_tests_trials = np.zeros(num_trials)
naiive_tests_trials = np.zeros(num_trials)

MB_NRMSE_trials = np.zeros(num_trials)
loc_NRMSE_trials = np.zeros(num_trials)

OLS_NRMSE_trials = np.zeros(num_trials)

lg_stepsizes = [np.exp(exponent) for exponent in np.linspace(-8,1,n_stepsizes)] #MB SGD #bigger range than log reg because optimum uncertain: D and L both very big
lc_stepsizes = [np.exp(exponent) for exponent in np.linspace(-10,0,n_stepsizes)] #Local SGD
gstepLproduct = list(itertools.product(lg_stepsizes, Ls))
cstepLproduct = list(itertools.product(lc_stepsizes, Ls))
        
if DO_COMPUTE:
    for trial in range(num_trials):
        print("DOING TRIAL", trial)
        train_features_by_machine, train_labels_by_machine, test_features_by_machine, test_labels_by_machine = splitdata(N)
        train_features, train_labels =  pd.concat(train_features_by_machine), pd.concat(train_labels_by_machine)#aggregate data (not by machine)
        test_features, test_labels = pd.concat(test_features_by_machine), pd.concat(test_labels_by_machine)
        def f_eval(w):
            return F_eval(w, train_features, train_labels)
        
        def test_eval(w):
            return F_eval(w, test_features, test_labels)

        def grad_eval(w, minibatch_size, m): #stochastic (minibatch) grad eval  
            idxs = np.random.randint(0, train_features_by_machine[m].shape[0], minibatch_size) 
            return squared_loss_gradient(w, train_features_by_machine[m].iloc[idxs, ::], train_labels_by_machine[m].iloc[idxs]) #returns average gradient across minibatch of size minibatch_size (=K)

        def full_grad_eval(w):
            return squared_loss_gradient(w, train_features, train_labels)

        def hessian_eval(w):
            return squared_loss_hessian(w, train_features, train_labels)
        #Newton to compute Fstar, wstar, and upsilon:
        Fstar, wstar = newtons_method(x_len, f_eval, full_grad_eval, hessian_eval)
        for m in range(M):
            nrm_nabla_Fm_star = np.linalg.norm(squared_loss_gradient(wstar, train_features.loc[list(train_labels_by_machine[m].index), ::], train_labels.loc[list(train_labels_by_machine[m].index)]))
            upsilon[trial] += nrm_nabla_Fm_star**2 / M
        print('Fstar = {:.6f}'.format(Fstar))
        print('upsilon^2 = {:.5f}'.format(upsilon[trial]))
        #Fstar_test = F_eval(wstar, test_features, test_labels)
        
        ###NAIIVE BASELINE (mean of target using all N clients' data)### [used to normalize reported errors]
        naiive = np.average(train_labels)
        naiive_tests_trials[trial] = (np.linalg.norm(test_labels - naiive*np.ones(len(test_labels)))**2)/(2*len(test_labels))
        
#         #####(non-private) OLS### 
#         mod = sm.OLS(train_labels, train_features)
#         res = mod.fit()
# #print(res.summary()) 
# #rss = res.ssr
# #print('train RSS is', rss)

# #make predictions on test data: 
#         yhat_test =  res.predict(test_features)
#         test_residuals = test_labels - yhat_test 

#         #test error (test RSS):
#         OLS_test_RSS = np.linalg.norm(test_residuals)**2
# #print('test_RSS is', test_RSS) 
#         OLS_test_MSE = OLS_test_RSS/len(test_labels)
#         OLS_NRMSE_trials[trial] = np.sqrt(OLS_test_MSE/naiive_tests_trials[trial])
        
        
        #####NON PRIVATE Distributed ALGS######
        print('Doing Minibatch SGD...') #for each stepsize option, compute average excess risk of MBSGD over n_reps trials
        MB_results = np.zeros(len(gstepLproduct))
        local_results = np.zeros(len(cstepLproduct))
        #MB_trains = np.zeros(len(gstepLproduct))
        #local_trains = np.zeros(len(cstepLproduct)) 
        MB_tests = np.zeros(len(gstepLproduct))
        local_tests = np.zeros(len(cstepLproduct)) 
        for i, (stepsize, L) in enumerate(gstepLproduct):
            #w = np.zeros(dim)
            print('Stepsize {:.5f}:  {:d}/{:d}, L{:d}'.format(stepsize, i+1, len(gstepLproduct), L))
            for rep in range(n_reps):
                iterates, l, success = minibatch_sgd(x_len, M, Mavail, K, R, stepsize, loss_freq, f_eval, grad_eval, L)
                if success == 'converged':
                    MB_results[i] += (l[-1] - Fstar) / n_reps #average excess risk val over the n_reps= 4 trials 
                    MB_tests[i] += F_eval(np.average(iterates, axis=0), test_features, test_labels)/n_reps
                else:
                    MB_results[i] += 5000000000
                    MB_tests[i] += 5000000000
        MB_ls[trial] = np.min(MB_results) 
        MB_step_index = np.argmin(MB_results) 
        #noisyMB_w_opt = noisyMB_w[noisyMB_step_index]
        MB_tests_trials[trial] = MB_tests[MB_step_index]
        MB_NRMSE_trials[trial] = np.sqrt(MB_tests_trials[trial]/naiive_tests_trials[trial])
        print('Doing Local SGD...') #for each stepsize option, compute average excess risk of LocalSGD over 4 trials
        for i, (stepsize, L) in enumerate(cstepLproduct):
            #w = np.zeros(dim)
            print('Stepsize {:.5f}:  {:d}/{:d}, L{:d}'.format(stepsize, i+1, len(cstepLproduct), L))
            for rep in range(n_reps):
                iterates, l, success = local_sgd(x_len, M, Mavail, K, R, stepsize, loss_freq, f_eval, grad_eval, L)
                if success == 'converged':
                    local_results[i] += (l[-1] - Fstar) / n_reps #average excess risk over the n_reps= 4 trials
                    #w += np.average(iterates,axis=0) / n_reps 
                    local_tests[i] += F_eval(np.average(iterates, axis=0), test_features, test_labels)/n_reps
                else:
                    local_results[i] += 5000000000
                    local_tests[i] += 5000000000
        local_ls[trial] = np.min(local_results) 
        local_stepL_index = np.argmin(local_results)  
        loc_tests_trials[trial] = local_tests[local_stepL_index]
        loc_NRMSE_trials[trial] = np.sqrt(loc_tests_trials[trial]/naiive_tests_trials[trial])
        
    ####Noisy algorithms####
        noisyMB_trains = {}
        noisyMB_tests = {}
        noisyloc_trains = {}
        noisyloc_tests = {}
        for eps in epsilons:
            noisyMB_trains[eps] = np.zeros(len(gstepLproduct)) 
            noisyMB_tests[eps]= np.zeros(len(gstepLproduct))
            noisyloc_trains[eps]=np.zeros(len(cstepLproduct))
            noisyloc_tests[eps]=np.zeros(len(cstepLproduct)) 
        
        for eps in epsilons:
            print('\n\nDOING eps = {:f}'.format(eps))
            print('Doing Noisy MB SGD...') #for each stepsize option, compute average excess risk of MBSGD over 4 trials
            noisyMB_results = np.zeros(len(gstepLproduct)) 
            noisyloc_results = np.zeros(len(cstepLproduct)) 
            for i, (stepsize, L) in enumerate(gstepLproduct): 
            #w = np.zeros(dim)
                print('Stepsize {:.5f}:  {:d}/{:d}, L{:d}'.format(stepsize, i+1, len(gstepLproduct), L))
                for rep in range(n_reps): #n_reps=3 trials for each stepsize
                    iterates, l, success = ACnoisyMB_sgd(eps, L, x_len, M, Mavail, K, R, stepsize, loss_freq, f_eval, grad_eval)
                    if success == 'converged':
                        noisyMB_results[i] += (l[-1] - Fstar) / n_reps 
                        noisyMB_tests[eps][i] += F_eval(np.average(iterates, axis=0), test_features, test_labels)/n_reps
                    else:
                            noisyMB_results[i] += 5000000000
                            noisyMB_tests[eps][i] += 5000000000
            noisy_MB_l = np.min(noisyMB_results)  
            noisyMB_ls[eps][trial] = noisy_MB_l 
            noisyMB_step_index = np.argmin(noisyMB_results) 
            t = noisyMB_tests[eps][noisyMB_step_index] 
            print("noisy MB test error for trial {:d} is".format(trial), t)
            noisyMB_tests_trials[eps][trial] = t
            noisyMB_NRMSE_trials[eps][trial] = np.sqrt(noisyMB_tests_trials[eps][trial]/naiive_tests_trials[trial])
        
            print('Doing Noisy Local GD...')  
            for i, (stepsize, L) in enumerate(cstepLproduct): 
            #w = np.zeros(dim)
                print('Stepsize {:.5f}:  {:d}/{:d}, L{:d}'.format(stepsize, i+1, len(cstepLproduct), L))
                for rep in range(n_reps):
                    iterates, l, success = ACnoisy_local_sgd(eps, L, x_len, M, Mavail, K, R, stepsize, loss_freq, f_eval, grad_eval)
                    if success == 'converged':
                        noisyloc_results[i] += (l[-1] - Fstar) / n_reps  
                        noisyloc_tests[eps][i] += F_eval(np.average(iterates, axis=0), test_features, test_labels)/n_reps
                    else:
                        noisyloc_results[i] += 5000000000 
                        noisyloc_tests[eps][i] += 5000000000 
            noisy_loc_l = np.min(noisyloc_results)
            noisylocal_ls[eps][trial] = noisy_loc_l 
            noisyloc_stepL_index = np.argmin(noisyloc_results)
            u = noisyloc_tests[eps][noisyloc_stepL_index] 
            print("noisy loc test error for trial {:d} is".format(trial), u)
            noisyloc_tests_trials[eps][trial] = u
            noisyloc_NRMSE_trials[eps][trial] = np.sqrt(noisyloc_tests_trials[eps][trial]/naiive_tests_trials[trial])
            


 #########PLOTS########
 
 ###error bar versions###
fig = plt.figure()
ax = fig.add_subplot(111)
#lower_p = 2.5
#upper_p = 97.5
lower_p = 5
upper_p = 95

#Noisy MB SGD#
noisyMB_errs = np.zeros(len(epsilons))
noisyMB_means = {}
noisyMB_lows = {}
noisyMB_his = {}
for e, eps in enumerate(epsilons):
    noisyMB_means[eps] = np.average(noisyMB_NRMSE_trials[eps])
    noisyMB_lows[eps] = max(0.0, percentile(noisyMB_NRMSE_trials[eps], lower_p))
    noisyMB_his[eps] = min(1.0, percentile(noisyMB_NRMSE_trials[eps], upper_p))
    noisyMB_errs[e] = (noisyMB_his[eps] - noisyMB_lows[eps])/2

noisyMB_means_sorted = list(zip(*sorted(noisyMB_means.items())))[1] 
ax.errorbar(epsilons, noisyMB_means_sorted, yerr = noisyMB_errs, color = '#1f77b4', ecolor='lightblue', mfc='#1f77b4',
          mec='#1f77b4', capsize = 10, label='Noisy MB SGD after {:d} rounds'.format(R))

#Noisy Local SGD#
noisyloc_errs = np.zeros(len(epsilons))
noisyloc_means = {}
noisyloc_lows = {}
noisyloc_his = {}
for e, eps in enumerate(epsilons):
    noisyloc_means[eps] = np.average(noisyloc_NRMSE_trials[eps])
    noisyloc_lows[eps] = max(0.0, percentile(noisyloc_NRMSE_trials[eps], lower_p))
    noisyloc_his[eps] = min(1.0, percentile(noisyloc_NRMSE_trials[eps], upper_p))
    noisyloc_errs[e] = (noisyloc_his[eps] - noisyloc_lows[eps])/2

noisyloc_means_sorted = list(zip(*sorted(noisyloc_means.items())))[1] 
ax.errorbar(epsilons, noisyloc_means_sorted, yerr = noisyloc_errs, color = '#ff7f0e', ecolor='navajowhite', mfc='#ff7f0e',
          mec='#ff7f0e',  capsize = 10, label='Noisy Local SGD after {:d} rounds'.format(R))


#MB SGD#
MB_errs = np.zeros(len(epsilons))
MB_mean = np.average(MB_NRMSE_trials)
MB_low = max(0.0, percentile(MB_NRMSE_trials, lower_p))
MB_hi = min(1.0, percentile(MB_NRMSE_trials, upper_p))
for e, eps in enumerate(epsilons):
    MB_errs[e] = (MB_hi - MB_low)/2
ax.errorbar(epsilons, [MB_mean]*len(epsilons), yerr = MB_errs, color = '#2ca02c', ecolor='lightgreen', mfc='#2ca02c',
            mec='#2ca02c', capsize = 10,  label = 'MB SGD after {:d} rounds'.format(R))

#Local SGD#
loc_errs = np.zeros(len(epsilons))
loc_mean = np.average(loc_NRMSE_trials)
loc_low = max(0.0, percentile(loc_NRMSE_trials, lower_p))
loc_hi = min(1.0, percentile(loc_NRMSE_trials, upper_p))
for e, eps in enumerate(epsilons):
    loc_errs[e] = (loc_hi - loc_low)/2
ax.errorbar(epsilons, [loc_mean]*len(epsilons), yerr = loc_errs, color = '#d62728', ecolor='lightcoral', mfc='#d62728',
          mec='#d62728',  capsize = 10, label = 'Local SGD after {:d} rounds'.format(R))


handles,labels = ax.get_legend_handles_labels()
ax.set_xlabel(r'$\epsilon$')
#ax.set_ylabel('Avg. Test Error ({:d} Trials)'.format(num_trials))
ax.set_ylabel('Relative Test RMSE ({:d} Trials)'.format(num_trials)) 
#ax.set_title('K = {:d}, $\upsilon$={:.2f}, {:d} Trials'.format(K, np.average(upsilon), num_trials))  
ax.set_title(r'N = {:d}, M = {:d}, K = {:d}, $\upsilon_*^2$={:.1f}'.format(N, Mavail, K, np.average(upsilon)))
ax.legend(handles, labels, loc='upper right')
plt.savefig('plots' + path + 'errorbar_lin_test_error_vs_epsilon.svg', dpi=400)
plt.show()

# ###no error bars version###
# ###PLOT test error vs. epsilon###
# fig2 = plt.figure()
# ax2 = fig2.add_subplot(111)
# noisyMB_test_errors_sorted = sorted(noisyMB_tests_trials.items()) # sorted by key, return a list of tuples
# noisyloc_test_errors_sorted = sorted(noisyloc_tests_trials.items())
# l = list(zip(*noisyMB_test_errors_sorted))[1]
# m = []
# for i in range(len(l)):
#     m.append(np.average(l[i]))
# l2 = list(zip(*noisyloc_test_errors_sorted))[1]
# m2 = []
# for i in range(len(l2)):
#     m2.append(np.average(l2[i]))

# ax2.plot(epsilons, m, label='Noisy MB SGD after {:d} rounds'.format(R))
# ax2.plot(epsilons, m2,label='Noisy Local SGD after {:d} rounds'.format(R))
# ax2.plot(epsilons, [np.average(MB_tests_trials)]*len(epsilons), label = 'MB SGD after {:d} rounds'.format(R))
# ax2.plot(epsilons, [np.average(loc_tests_trials)]*len(epsilons), label = 'Local SGD after {:d} rounds'.format(R))
# handles,labels = ax2.get_legend_handles_labels()
# ax2.set_xlabel(r'$\epsilon$')
# #ax2.set_ylabel('Avg. Test Error ({:d} Trials)'.format(num_trials)) 
# ax2.set_ylabel('Relative Test RMSE ({:d} Trials)'.format(num_trials)) 
# ax2.set_title(r'N = {:d}, M = {:d}, K = {:d}, $\upsilon_*^2$={:.1f}'.format(N, Mavail, K, np.average(upsilon)))
# ax2.legend(handles, labels, loc='upper right')
# plt.savefig('plots' + path + 'lin_test_error_vs_epsilon.svg', dpi=400)
# plt.show()

###SAVE RESULTS###
# print("noisy MB test squared errors", noisyMB_tests_trials)
# print("noisy loc test squared errors", noisyloc_tests_trials)
# print("MB test sq. errors", MB_tests_trials)
# print("local SGD test sq. errors", loc_tests_trials)
# print("naiive test sq. errors", naiive_tests_trials)


# create json objects from dictionaries/arrays
#NRMSE  
#convert arrays within dictionaries to lists (before json)
noisyMB_NRMSE_trials_lists = {}
noisyloc_NRMSE_trials_lists = {}
for eps in epsilons:
    noisyMB_NRMSE_trials_lists[eps] = noisyMB_NRMSE_trials[eps].tolist()
    noisyloc_NRMSE_trials_lists[eps] = noisyloc_NRMSE_trials[eps].tolist()
noisyMB_NRMSE_trials_json = json.dumps(noisyMB_NRMSE_trials_lists)
noisyloc_NRMSE_trials_json = json.dumps(noisyloc_NRMSE_trials_lists)

MB_NRMSE_trials_list = MB_NRMSE_trials.tolist() 
MB_NRMSE_trials_json = json.dumps(MB_NRMSE_trials_list)
loc_NRMSE_trials_list = loc_NRMSE_trials.tolist() 
loc_NRMSE_trials_json = json.dumps(loc_NRMSE_trials_list)

#MSE 
noisyMB_tests_trials_lists = {}
noisyloc_tests_trials_lists = {}
for eps in epsilons:
    noisyMB_tests_trials_lists[eps] = noisyMB_tests_trials[eps].tolist()
    noisyloc_tests_trials_lists[eps] = noisyloc_tests_trials[eps].tolist()
noisyMB_tests_trials_json = json.dumps(noisyMB_tests_trials_lists)
noisyloc_tests_trials_json = json.dumps(noisyloc_tests_trials_lists)

MB_tests_trials_list = MB_tests_trials.tolist() 
MB_tests_trials_json = json.dumps(MB_tests_trials_list)
loc_tests_trials_list = loc_tests_trials.tolist() 
loc_tests_trials_json = json.dumps(loc_tests_trials_list)
#naiive
naiive_tests_trials_list = naiive_tests_trials.tolist() 
naiive_tests_trials_json = json.dumps(naiive_tests_trials_list)

#upsilons
upsilon_list = upsilon.tolist() 
upsilon_json = json.dumps(upsilon_list)


# open file for writing, "w" 
f = open(path + "results.json","w")

# write json object to file
f.write("noisyMB_NRMSE:" + noisyMB_NRMSE_trials_json)
f.write("\n\n")
f.write("noisyloc_NRMSE:" + noisyloc_NRMSE_trials_json)
f.write("\n\n")
f.write("MB_NRMSE:" + MB_NRMSE_trials_json)
f.write("\n\n")
f.write("loc_NRMSE:" + loc_NRMSE_trials_json)
f.write("\n\n")

f.write("noisyMB_MSE:" + noisyMB_tests_trials_json)
f.write("\n\n")
f.write("noisyloc_MSE:" + noisyloc_tests_trials_json)
f.write("\n\n")
f.write("MB_MSE:" + MB_tests_trials_json)
f.write("\n\n")
f.write("loc_MSE:" + loc_tests_trials_json)
f.write("\n\n")

f.write("naiive MSE:"+naiive_tests_trials_json)
f.write("\n\n")

f.write("upsilons:" + upsilon_json)
# close file
f.close()
