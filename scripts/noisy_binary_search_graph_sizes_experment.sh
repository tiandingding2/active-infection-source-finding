python query_count_vs_graph_size.py -t grid -b 2 --emin 2 --emax 7 noisy_bs
python query_count_vs_graph_size.py -t er -b 2 --emin 6 --emax 13 noisy_bs
python query_count_vs_graph_size.py -t barabasi -b 2 --emin 6 --emax 13 noisy_bs
python query_count_vs_graph_size.py -t kr-hier -b 10 --emin 8 --emax 13 noisy_bs
python query_count_vs_graph_size.py -t kr-peri -b 10 --emin 8 --emax 13 noisy_bs
python query_count_vs_graph_size.py -t kr-rand -b 10 --emin 8 --emax 13 noisy_bs
python query_count_vs_graph_size.py -t pl-tree -b 2 --emin 4 --emax 13 noisy_bs

