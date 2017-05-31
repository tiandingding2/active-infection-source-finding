import numpy as np
import pytest
from graph_tool.all import load_graph

from steiner_tree_greedy import steiner_tree_greedy
from utils import earliest_obs_node
from feasibility import is_feasible
from cascade import gen_nontrivial_cascade

QS = np.linspace(0.1, 1.0, 10)
MODELS = ['si', 'ic', 'sp']

P = 0.5
K = 10


@pytest.fixture
def cascades_on_tree():
    cascades = []
    g = load_graph('data/grid/2-6/graph.gt')
    for model in MODELS:
        for q in QS:
            for i in range(K):
                ret = gen_nontrivial_cascade(
                    g, P, q, model=model, return_tree=True,
                    source_includable=True)
                ret = (g, ) + ret + (model, q, i)
                cascades.append(ret)  # g, infection_times, source, obs_nodes, true_tree
    return cascades
        

def test_greedy(cascades_on_tree):
    for g, infection_times, source, obs_nodes, true_tree, model, q, i in cascades_on_tree:
        print(model, q, i)
        root = earliest_obs_node(obs_nodes, infection_times)
        tree = steiner_tree_greedy(
            g, root, infection_times, source, obs_nodes,
            debug=False,
            verbose=True
        )
        assert is_feasible(tree, root, obs_nodes, infection_times)
