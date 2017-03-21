import math
import networkx as nx
import numpy as np
import pandas as pd
import os
from tempfile import NamedTemporaryFile
from scipy.sparse import csr_matrix
from joblib import Parallel, delayed
import pickle as pkl
from tqdm import tqdm


def sample_graph_from_infection(g):
    rands = np.random.rand(g.number_of_edges())
    active_edges = [(u, v) for (u, v), r in zip(g.edges_iter(), rands) if g[u][v]['p'] >= r]
    induced_g = nx.Graph()
    induced_g.add_nodes_from(g.nodes())
    induced_g.add_edges_from(active_edges)
    for u, v in induced_g.edges_iter():
        induced_g[u][v]['d'] = g[u][v]['d']
    return induced_g


def make_full_cascade(g, source=None, is_sampled=False):
    """
    """
    if source is None:
        idx = np.arange(g.number_of_nodes())
        source = g.nodes()[np.random.choice(idx)]

    if not is_sampled:
        induced_g = sample_graph_from_infection(g)
    else:
        induced_g = g
        
    if not induced_g.has_node(source):
        infection_times = {n: float('inf') for n in g.nodes_iter()}
        infection_times[source] = 0
    else:
        infection_times = nx.shortest_path_length(induced_g, source=source, weight='d')
        for n in g.nodes_iter():
            if n not in infection_times:
                infection_times[n] = float('inf')
    assert infection_times[source] == 0
    assert len(infection_times) == g.number_of_nodes()
    return infection_times


def make_partial_cascade(g, fraction, sampling_method='uniform'):
    """simulate one IC cascade and return the source, infection times and infection tree"""
    while True:
        infection_times = make_full_cascade(g)
        tree = None  # compatibility reason

        cascade_size = np.count_nonzero(np.invert(np.isinf(list(infection_times.values()))))

        sample_size = math.ceil(cascade_size * fraction)
        infected_nodes = [n for n in g.nodes_iter() if not np.isinf(infection_times[n])]
        
        if len(infected_nodes) > sample_size:
            break
        
    if sampling_method == 'uniform':
        idx = np.arange(len(infected_nodes))
        sub_idx = np.random.choice(idx, sample_size)
        obs_nodes = set([infected_nodes[i] for i in sub_idx])
    elif sampling_method == 'late_nodes':
        obs_nodes = set(sorted(infected_nodes, key=lambda n: -infection_times[n])[:sample_size])
    else:
        raise ValueError('unknown sampling methods')

    assert len(obs_nodes) > 0
    source = min(infection_times, key=lambda n: infection_times[n])

    return source, obs_nodes, infection_times, tree


def run_one_round(sampled_g, node2id):

    f = NamedTemporaryFile(mode='w', delete=False)
    for s in sampled_g.nodes_iter():
        s2t_len = nx.shortest_path_length(sampled_g, source=s)
        f.write('\n'.join('{},{},{}'.format(node2id[s], node2id[n], t)
                          for n, t in s2t_len.items()))
        f.write('\n')
    f.close()
    return f.name
    
    # return np.array([np.array([node2id[s], node2id[n], t],
    #                           dtype=np.uint16)
    #                  for s in s2t_len
    #                  for n, t in s2t_len[s].items()],
    #                 dtype=np.uint16)
# @profile
def run_for_source(s, sampled_graphs_path, node2id):
    """return:
    sparse matrix N by t_{max}+2, t_{max} is the maximum time.
    """
    sampled_graphs = pkl.load(open(sampled_graphs_path, 'rb'))
    n_rounds = len(sampled_graphs)
    n_nodes = sampled_graphs[0].number_of_nodes()
    NT = n_rounds * n_nodes
    
    col = np.empty(0, dtype=np.int16)
    for g in sampled_graphs:
        sp_len = nx.shortest_path_length(g, source=s)
        col = np.concatenate((col,
                             np.array([sp_len.get(n, -1)
                                       for n in g.nodes_iter()],
                                      dtype=np.int16)))
    col = np.array(col, dtype=np.int16)
    max_time = col.max()
    col[col == -1] = max_time + 1
    shape = (n_nodes, max_time + 2)

    row = np.array([node2id[n]
                    for g in sampled_graphs
                    for n in g.nodes_iter()],
                   dtype=np.uint16)
    data = np.ones(NT, dtype=np.float) / n_rounds
    return node2id[s], csr_matrix((data, (row, col)),
                         shape=shape)
    

def infection_time_estimation(g, n_rounds, return_node2id=False):
    """
    estimate the infection time distribution
    n_rounds of cascades for *each* node

    Returns:
    dict of source to 2D sparse matrices (node to infection time probabilities)
        can be viewed as 3D tensor:
        N x N x max(t), source to node to infection time
        dict source to nodes' infection time distribution
    """
    node2id = {n: i for i, n in enumerate(g.nodes_iter())}

    if True:
        # paralel for each source
        # more memory saving
        sampled_graphs = Parallel(n_jobs=-1)(delayed(sample_graph_from_infection)(g)
                                             for i in range(n_rounds))
        f = NamedTemporaryFile(mode='wb', delete=False)
        
        pkl.dump(sampled_graphs, f)
        f.close()
        sampled_graphs_path = f.name

        if True:
            # parallel
            s2csr_matrix = Parallel(n_jobs=-1)(
                delayed(run_for_source)(s, sampled_graphs_path, node2id)
                for s in tqdm(g.nodes_iter()))
            d = {s: m for s, m in s2csr_matrix}
        else:
            # serial
            d = {}
            for s in tqdm(g.nodes_iter()):
                d[s] = run_for_source(s, sampled_graphs_path, node2id)
        os.unlink(sampled_graphs_path)
    elif False:
        # parallel and pandas.Dataframe approach
        # faster but more memory consuming
        tmp_file_paths = Parallel(n_jobs=-1)(delayed(run_one_round)(sample_graph_from_infection(g), node2id)
                                             for i in range(n_rounds))
        dfs = [pd.read_csv(p, sep=',',
                           names=['source', 'node', 'time'],
                           dtype=np.uint16)
               for p in tmp_file_paths]
        df = pd.concat(dfs, axis=0)
        del dfs
        # remove files
        for p in tmp_file_paths:
            os.unlink(p)

        n_times = df['time'].max() + 2
        d = {}

        for s, sdf in tqdm(df.groupby('source')):
            nt_series = pd.Series([(n, t) for n, t in zip(sdf['node'], sdf['time'])])
            counts = nt_series.value_counts()
        
            row = [r for r, _ in counts.index]
            col = [c for _, c in counts.index]
            # row, col = zip(*counts.index.tolist())

            row = np.array(row)
            col = np.array(col)
            
            # get uninfected counts
            sum_df = pd.DataFrame.from_dict({'r': row, 'c': counts.as_matrix()})
            row_sums = sum_df.groupby('r')['c'].sum()

            uninfected_counts = (np.ones(g.number_of_nodes(), dtype=np.float) * n_rounds -
                                 row_sums.as_matrix())
            data = np.concatenate((counts.as_matrix(),
                                   uninfected_counts))
            data /= n_rounds
            row = np.concatenate((row,
                                  np.arange(g.number_of_nodes())))
            col = np.concatenate((col,
                                  (n_times-1) * np.ones(g.number_of_nodes())))
            
            d[s] = csr_matrix((data, (row, col)),
                              shape=(g.number_of_nodes(), n_times))
    else:
        # vanilla approach
        # might spend less memory
        s2n_times_counter = defaultdict(lambda: defaultdict(int))

        inf = float('inf')
        # run in serial to save memory
        for i in tqdm(range(n_rounds)):
            sampled_g = sample_graph_from_infection(g)
            # this is using Dijkstra
            # s2t_len = nx.shortest_path_length(sampled_g, weight='d')

            # this is serial BFS
            s2t_len = nx.shortest_path_length(sampled_g)

            # this is parallel BFS (slow)
            # results = Parallel(n_jobs=-1)(
            #     delayed(nx.single_source_shortest_path_length)(g, n)
            #     for n in g.nodes_iter())
            # s2t_len = {n: t_len for n, t_len in zip(g.nodes_iter(), results)}
            
            for s in s2t_len:  # one cascade for each node
                for n in sampled_g.nodes_iter():
                    s2n_times_counter[(s, n)][s2t_len[s].get(n, inf)] += 1

        all_times = np.array([t
                              for times_counter in s2n_times_counter.values()
                              for t in times_counter.keys()])
        all_times = np.ravel(all_times)
        unique_values = np.unique(all_times)

        min_val, max_val = (int(unique_values.min()),
                            int(unique_values[np.invert(np.isinf(unique_values))].max()))
        n_times = max_val - min_val + 2
        # using dict to 2D sparse matrix because there is no 3D sparse matrix
        d = dict()
        for s in tqdm(g.nodes_iter()):
            i = node2id[s]
            row = []  # infected node
            col = []  # infection time
            data = []  # probabilities
            for n in g.nodes_iter():
                j = node2id[n]
                cnts = s2n_times_counter[(s, n)]
                cnts[n_times-1] = cnts[float('inf')]
                del cnts[float('inf')]
                row += [j] * len(cnts)
                col_slice, cnts_list = map(list, zip(*cnts.items()))
                col += col_slice
                cnts_array = np.array(cnts_list, dtype=np.float)
                cnts_array /= cnts_array.sum()
                data += cnts_array.tolist()

            d[i] = csr_matrix((data, (row, col)), shape=(g.number_of_nodes(), n_times))

    if return_node2id:
        return d, node2id
    else:
        return d
