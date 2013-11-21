'''
Defines search operators and can expand kernels

Created Nov 2012

@authors: James Robert Lloyd (jrl44@cam.ac.uk)
          David Duvenaud (dkd23@cam.ac.uk)
          Roger Grosse (rgrosse@mit.edu)
'''

import itertools
import numpy as np

import model
        
# Search operators
MULTI_D_RULES = [('A', ('+', 'A', 'B'), {'A': 'kernel', 'B': 'base'}),
                 ('A', ('*', 'A', 'B'), {'A': 'kernel', 'B': 'base-not-const'}), # Might be generalised via excluded types?
                 ('A', ('*-const', 'A', 'B'), {'A': 'kernel', 'B': 'base-not-const'}),
                 ('A', 'B', {'A': 'kernel', 'B': 'base'}),
                 #('A', ('CP', 'A', 'd'), {'A': 'kernel', 'd' : 'dimension'}),
                 #('A', ('CB', 'A', 'd'), {'A': 'kernel', 'd' : 'dimension'}),
                 #('A', ('B', 'A', 'd'), {'A': 'kernel', 'd' : 'dimension'}),
                 #('A', ('BL', 'A', 'd'), {'A': 'kernel', 'd' : 'dimension'}),
                 ('A', ('None',), {'A': 'kernel'}),
                 ]
    
class MultiDGrammar:
    def __init__(self, ndim, base_kernels='SE', rules=MULTI_D_RULES):
        if (rules is None) or (rules == []):
            rules = MULTI_D_RULES
        self.rules = rules
        self.ndim = ndim
        self.base_kernels = base_kernels
        
    def type_matches(self, candidate, tp):
        if tp == 'base':
            return isinstance(candidate, model.Kernel) and (not candidate.is_operator)
        elif tp == 'kernel':
            return isinstance(candidate, model.Kernel)
        elif tp == 'base-not-const':
            return isinstance(candidate, model.Kernel) and (not candidate.is_operator) and (not isinstance(candidate, model.ConstKernel))
        elif tp == 'dimension':
            return isinstance(candidate, int)
        else:
            raise RuntimeError('Unknown type: %s' % tp)
        
    def list_options(self, tp):
        if tp == 'base':
            return list(model.base_kernels(self.ndim, self.base_kernels))
        elif tp == 'kernel':
            raise RuntimeError("Cannot expand the '%s' type" % tp)
        elif tp == 'base-not-const':
            return [k for k in self.list_options(tp='base') if not isinstance(k, model.ConstKernel)]
        elif tp == 'dimension':
            return range(self.ndim)
        else:
            raise RuntimeError('Unknown type: %s' % tp)
    
def replace_all(polish_expr, mapping):
    if type(polish_expr) == tuple:
        return tuple([replace_all(e, mapping) for e in polish_expr])
    elif type(polish_expr) == str:
        if polish_expr in mapping:
            return mapping[polish_expr].copy()
        else:
            return polish_expr
    else:
        assert isinstance(polish_expr, model.Kernel)
        return polish_expr.copy()
    
def polish_to_kernel(polish_expr):
    if type(polish_expr) == tuple:
        if polish_expr[0] == '+':
            operands = [polish_to_kernel(e) for e in polish_expr[1:]]
            return model.SumKernel(operands)
        elif polish_expr[0] == '*':
            operands = [polish_to_kernel(e) for e in polish_expr[1:]]
            return model.ProductKernel(operands)
        elif polish_expr[0] == '*-const':
            operands = [polish_to_kernel(e) for e in polish_expr[1:]]
            return model.ProductKernel([operands[0], model.SumKernel([operands[1], model.ConstKernel()])])
        elif polish_expr[0] == 'CP':
            base_kernel = polish_to_kernel(polish_expr[2])
            return model.ChangePointKernel(dimension=polish_expr[1], operands=[base_kernel, base_kernel.copy()])
        elif polish_expr[0] == 'CB':
            base_kernel = polish_to_kernel(polish_expr[2])
            return model.ChangeBurstKernel(dimension=polish_expr[1], operands=[base_kernel, base_kernel.copy()])
        elif polish_expr[0] == 'B':
            base_kernel = polish_to_kernel(polish_expr[2])
            return model.ChangeBurstKernel(dimension=polish_expr[1], operands=[model.ConstKernel(), base_kernel])
        elif polish_expr[0] == 'BL':
            base_kernel = polish_to_kernel(polish_expr[2])
            return model.ChangeBurstKernel(dimension=polish_expr[1], operands=[base_kernel, model.ConstKernel()])
        elif polish_expr[0] == 'None':
            return model.NoneKernel()
        else:
            raise RuntimeError('Unknown operator: %s' % polish_expr[0])
    else:
        assert isinstance(polish_expr, model.Kernel) or (polish_expr is None)
        return polish_expr


def expand_single_tree(kernel, grammar):
    assert isinstance(kernel, model.Kernel)
    result = []
    for lhs, rhs, types in grammar.rules:
        if grammar.type_matches(kernel, types[lhs]):
            free_vars = types.keys()
            assert lhs in free_vars
            free_vars.remove(lhs)
            choices = itertools.product(*[grammar.list_options(types[v]) for v in free_vars])
            for c in choices:
                mapping = dict(zip(free_vars, c))
                mapping[lhs] = kernel
                full_polish = replace_all(rhs, mapping)
                result.append(polish_to_kernel(full_polish))
    return result

def expand(kernel, grammar):
    result = expand_single_tree(kernel, grammar)
    if not kernel.is_operator:
        pass
    elif kernel.arity == 2:
        for i, op in enumerate(kernel.operands):
            for e in expand(op, grammar):
                new_ops = kernel.operands[:i] + [e] + kernel.operands[i+1:]
                new_ops = [op.copy() for op in new_ops]
                k = kernel.copy()
                k.operands = new_ops
                result.append(k)
    else:
        for subset in itertools.product(*((0,1),)*len(kernel.operands)):
            if (not sum(subset)==0) and (not sum(subset)==len(kernel.operands)):
                # Subset non-trivial
                unexpanded = [op for (i, op) in enumerate(kernel.operands) if not subset[i]]
                to_be_expanded = [op for (i, op) in enumerate(kernel.operands) if subset[i]]
                if len(to_be_expanded) > 1:
                    k = kernel.copy()
                    k.operands = to_be_expanded
                    to_be_expanded = k
                    # No need for redundant recursion of expanding sums
                    expansions = expand_single_tree(to_be_expanded, grammar)
                else:
                    to_be_expanded = to_be_expanded[0]
                    expansions = expand(to_be_expanded, grammar)
                for expanded in expansions:
                    new_ops = [expanded] + unexpanded
                    k = kernel.copy()
                    k.operands = new_ops
                    result.append(k)
    return result
    
def expand_kernels(D, seed_kernels, base_kernels='SE', rules=None):    
    '''Makes a list of all expansions of a set of kernels in D dimensions.'''
    g = MultiDGrammar(D, base_kernels=base_kernels, rules=rules)
    kernels = []
    for k in seed_kernels:
        kernels = kernels + expand(k, g)
    kernels = map(model.canonical, kernels)
    kernels = model.remove_duplicates(kernels)
    kernels = [k for k in kernels if not isinstance(k, model.NoneKernel)]
    return kernels

def expand_models(D, models, base_kernels='SE', rules=None):
    expanded = []
    for a_model in models:
        for k in expand_kernels(D, [a_model.kernel], base_kernels, rules):
            new_model = a_model.copy()
            new_model.kernel = k
            new_model.nll = np.nan
            expanded.append(new_model)
    return expanded 



            
