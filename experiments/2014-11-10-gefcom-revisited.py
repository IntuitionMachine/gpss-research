Experiment(description='Re-analysis of GEFCOM data for purposes of thesis',
           data_dir='../data/gefcom_temp',
           max_depth=10, 
           random_order=True,
           k=1,
           debug=False, 
           local_computation=False, 
           n_rand=9,
           sd=2, 
           jitter_sd=0.1,
           max_jobs=400, 
           verbose=False,
           make_predictions=False,
           skip_complete=True,
           results_dir='../results/2014-11-10-gefcom-revisited/',
           iters=250,
           base_kernels='SE,Per,Const,Noise',
           random_seed=9001,
           period_heuristic=3,
           max_period_heuristic=3,
           period_heuristic_type='min',
           subset=True,
           subset_size=250,
           full_iters=10,
           bundle_size=5,
           additive_form=True,
           mean='ff.MeanZero()',      # Starting mean
           kernel='ff.NoiseKernel()', # Starting kernel
           lik='ff.LikGauss(sf=-np.Inf)', # Starting likelihood
           score='bic',
           stopping_criteria=['no_improvement'],
           improvement_tolerance=0.1,
           search_operators=[('A', ('+', 'A', 'B'), {'A': 'kernel', 'B': 'base'}),
                             ('A', ('*', 'A', 'B'), {'A': 'kernel', 'B': 'base-not-const'}),
                             ('A', ('*-const', 'A', 'B'), {'A': 'kernel', 'B': 'base-not-const'}),
                             ('A', 'B', {'A': 'kernel', 'B': 'base'}),
                             ('A', ('None',), {'A': 'kernel'})])
