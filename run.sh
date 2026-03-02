python BasenoAgent.py --dataset cset --prompt detailed
python BasenoAgent.py --dataset cset --prompt concise
python BasenoAgent.py --dataset cset --prompt basic
python BasenoAgent.py --dataset gjopen --prompt detailed
python BasenoAgent.py --dataset gjopen --prompt concise
python BasenoAgent.py --dataset gjopen --prompt basic
python DynAgent.py --dataset cset --max_rounds 1 --max_experts 1
python DynAgent.py --dataset cset --max_rounds 5 --max_experts 1
python DynAgent.py --dataset cset --max_rounds 1 --max_experts 3
python DynAgent.py --dataset cset --max_rounds 5 --max_experts 3
python DynAgent.py --dataset cset --max_rounds 1 --max_experts 5
python DynAgent.py --dataset cset --max_rounds 5 --max_experts 5
python DynAgent.py --dataset gjopen --max_rounds 1 --max_experts 1
python DynAgent.py --dataset gjopen --max_rounds 5 --max_experts 1
python DynAgent.py --dataset gjopen --max_rounds 1 --max_experts 3
python DynAgent.py --dataset gjopen --max_rounds 5 --max_experts 3
python DynAgent.py --dataset gjopen --max_rounds 1 --max_experts 5
python DynAgent.py --dataset gjopen --max_rounds 5 --max_experts 5
python DebateAgent.py --dataset cset --max_rounds 1
python DebateAgent.py --dataset cset --max_rounds 3
python DebateAgent.py --dataset cset --max_rounds 5
python DebateAgent.py --dataset gjopen --max_rounds 1
python DebateAgent.py --dataset gjopen --max_rounds 3
python DebateAgent.py --dataset gjopen --max_rounds 5
