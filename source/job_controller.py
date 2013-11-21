'''
Main file for dispatching jobs to a cluster, creates remote files, etc.

@authors: David Duvenaud (dkd23@cam.ac.uk)
          James Robert Lloyd (jrl44@cam.ac.uk)
          Roger Grosse (rgrosse@mit.edu)
          
Created Jan 2013
'''

import model
from model import RegressionModel
import grammar
import gpml
import utils.latex
import utils.fear
try:
    import config
except:
    print '\n\nERROR : source/config.py not found\n\nPlease create it following example file as a guide\n\n'
    raise Exception('No config')
from utils import gaussians, psd_matrices

import numpy as np
nax = np.newaxis
import pylab
import scipy.io
import sys
import os
import tempfile
import subprocess
import time

import cblparallel
from cblparallel.util import mkstemp_safe
import re

import shutil
import random

def evaluate_models(models, X, y, verbose=True, iters=300, local_computation=False, zip_files=False, max_jobs=500, random_seed=0, subset=False, subset_size=250, full_iters=0, bundle_size=1):
    '''
    Sets up the kernel optimisation and nll calculation experiments, returns the results as scored kernels
    Input:
     - kernels           - A list of kernels (i.e. not scored kernels)
     - X                 - A matrix (data_points x dimensions) of input locations
     - y                 - A matrix (data_points x 1) of output values
     - ...
    Return:
     - A list of ScoredKernel objects
    '''
   
    # Make data into matrices in case they're unidimensional.
    if X.ndim == 1: X = X[:, nax]
    if y.ndim == 1: y = y[:, nax]
    ndata = y.shape[0]
    
    # Create data file
    if verbose:
        print 'Creating data file locally'
    data_file = cblparallel.create_temp_file('.mat')

    scipy.io.savemat(data_file, {'X': X, 'y': y, 'X_train' : X_train, 'y_train' : y_train})
    
    # Move to fear if necessary
    if not local_computation:
        if verbose:
            print 'Moving data file to fear'
        cblparallel.copy_to_remote(data_file)
    
    # Create a list of MATLAB scripts to assess and optimise parameters for each kernel
    if verbose:
        print 'Creating scripts'
    scripts = [None] * len(kernels)
    for (i, a_model) in enumerate(kernels):
        parameters = {'datafile': data_file.split('/')[-1],
                      'writefile': '%(output_file)s', # N.B. cblparallel manages output files
                      'gpml_path': cblparallel.gpml_path(local_computation),
                      'mean_syntax': a_model.mean.gpml_expression,
                      'mean_params': '[ %s ]' % ' '.join(str(p) for p in model.mean.param_vector),
                      'kernel_syntax': a_model.kernel.gpml_expression,
                      'kernel_params': '[ %s ]' % ' '.join(str(p) for p in model.kernel.param_vector),
                      'lik_syntax': a_model.likelihood.gpml_expression,
                      'lik_params': '[ %s ]' % ' '.join(str(p) for p in model.likelihood.param_vector),
                      'iters': str(iters),
                      'seed': str(np.random.randint(2**31)),
                      'subset': 'true' if subset else 'false',
                      'subset_size' : str(subset_size),
                      'full_iters' : str(full_iters)}

    ######
    ######
    ######
    # CONTINUE FROM HERE
    ######
    ######
    ######

        if zero_mean:
            if no_noise:
                scripts[i] = gpml.OPTIMIZE_KERNEL_CODE_ZERO_MEAN_NO_NOISE % parameters
            else:
                scripts[i] = gpml.OPTIMIZE_KERNEL_CODE_ZERO_MEAN % parameters
        else:
            scripts[i] = gpml.OPTIMIZE_KERNEL_CODE % parameters
        #### Need to be careful with % signs
        #### For the moment, cblparallel expects no single % signs - FIXME
        scripts[i] = re.sub('% ', '%% ', scripts[i])
    
    # Send to cblparallel and save output_files
    if verbose:
        print 'Sending scripts to cblparallel'
    if local_computation:
        output_files = cblparallel.run_batch_locally(scripts, language='matlab', max_cpu=1.1, job_check_sleep=5, submit_sleep=0.1, max_running_jobs=10, verbose=verbose)  
    else:
        output_files = cblparallel.run_batch_on_fear(scripts, language='matlab', max_jobs=max_jobs, verbose=verbose, zip_files=zip_files, bundle_size=bundle_size)  
    
    # Read in results
    results = [None] * len(kernels)
    for (i, output_file) in enumerate(output_files):
        if verbose:
            print 'Reading output file %d of %d' % (i + 1, len(kernels))
        results[i] = ScoredKernel.from_matlab_output(gpml.read_outputs(output_file), kernels[i].family(), ndata)
    
    # Tidy up local output files
    for (i, output_file) in enumerate(output_files):
        if verbose:
            print 'Removing output file %d of %d' % (i + 1, len(kernels)) 
        os.remove(output_file)
    # Remove temporary data file (perhaps on the cluster server)
    cblparallel.remove_temp_file(data_file, local_computation)
    
    # Return results i.e. list of ScoredKernel objects
    return results     

   
def make_predictions(X, y, Xtest, ytest, best_scored_kernel, local_computation=False, max_jobs=500, verbose=True, zero_mean=False, random_seed=0, no_noise=False):
    '''
    Evaluates a kernel on held out data
    Input:
     - X                  - A matrix (data_points x dimensions) of input locations
     - y                  - A matrix (data_points x 1) of output values
     - Xtest              - Held out X data
     - ytest              - Held out y data
     - best_scored_kernel - A Scored Kernel object to be evaluated on the held out data
     - ...
    Return:
     - A dictionary of results from the MATLAB script containing:
       - loglik - an array of log likelihoods of test data
       - predictions - an array of mean predictions for the held out data
       - actuals - ytest
       - model - I'm not sure FIXME
       - timestamp - A time stamp of some sort
    '''
    # Make data into matrices in case they're unidimensional.
    if X.ndim == 1: X = X[:, nax]
    if y.ndim == 1: y = y[:, nax]
    ndata = y.shape[0]
    # Save temporary data file in standard temporary directory
    data_file = cblparallel.create_temp_file('.mat')
    scipy.io.savemat(data_file, {'X': X, 'y': y, 'Xtest' : Xtest, 'ytest' : ytest})
    # Copy onto cluster server if necessary
    if not local_computation:
        if verbose:
            print 'Moving data file to fear'
        cblparallel.copy_to_remote(data_file)
    # Create prediction code
    parameters ={'datafile': data_file.split('/')[-1],
                 'writefile': '%(output_file)s',
                 'gpml_path': cblparallel.gpml_path(local_computation),
                 'kernel_family': best_scored_kernel.k_opt.gpml_kernel_expression(),
                 'kernel_params': '[ %s ]' % ' '.join(str(p) for p in best_scored_kernel.k_opt.param_vector()),
                 'noise': str(best_scored_kernel.noise),
                 'iters': str(30),
                 'seed': str(random_seed)}
    if zero_mean:
        if no_noise:
            code = gpml.PREDICT_AND_SAVE_CODE_ZERO_MEAN_NO_NOISE % parameters
        else:
            code = gpml.PREDICT_AND_SAVE_CODE_ZERO_MEAN % parameters
    else:
        code = gpml.PREDICT_AND_SAVE_CODE % parameters
    code = re.sub('% ', '%% ', code) # HACK - cblparallel currently does not like % signs
    # Evaluate code - potentially on cluster
    if local_computation:   
        temp_results_file = cblparallel.run_batch_locally([code], language='matlab', max_cpu=1.1, max_mem=1.1, verbose=verbose)[0]
    else:
        temp_results_file = cblparallel.run_batch_on_fear([code], language='matlab', max_jobs=max_jobs, verbose=verbose)[0]
    results = scipy.io.loadmat(temp_results_file)
    # Remove temporary files (perhaps on the cluster server)
    cblparallel.remove_temp_file(temp_results_file, local_computation)
    cblparallel.remove_temp_file(data_file, local_computation)
    # Return dictionary of MATLAB results
    return results


