# Question Answering as Programming for Solving Time-Sensitive Questions (EMNLP 2023)

<img src="./images/main_figure.png" alt="Image  Title" style="zoom: 100%;" />

# Setup
1. `pip install -r requirements.txt`
2. Set the openai api key in `main.py`

# Quick Start
Run TimeQA experiments
```
python main.py 
  --prompt_file timeqa.json \
  --given_context 1 \
  --dataset timeqa \
  --data_file test_hard.jsonl \
  --max_slice_length 512 \
  --slice_stride 384 \
  --return_search_passage content \
  --model_name gpt-3.5-turbo \
  --resume_id -1 
```

Run TempQuestions and TimeQuestions experiments
```
python main.py 
  --prompt_file timequestions.json \
  --given_context 0 \
  --dataset tempquestion \
  --data_file test.jsonl \
  --max_slice_length 512 \
  --slice_stride 384 \
  --return_search_passage content \
  --model_name gpt-3.5-turbo \
  --resume_id -1 
```

The output should look like
```
0 Joachim Löw was the coach of which team between Jan 1997 and Aug 1997?
'''python
query = {"subject": "Joachim Löw", "relation": "coach of", "object": None, "time": {"start": datetime(1997, 1, 1), "end": datetime(1997, 8, 31)}}
answer_key = "object"
'''
Search:
'''python
entities_to_search = ["Joachim Löw"]
'''
--------------------------------------------------
Generate a background document from Wikipedia to answer the given question:Joachim Löw is a German football coach and former player. He was the head coach of VfB Stuttgart from July 1996 to October 1998.
Extract information relevant to the query:
'''python
information.append({"subject": "Joachim Löw", "relation": "coach of", "object": "VfB Stuttgart", "time": {"start": datetime(1996, 7, 1), "end": datetime(1998, 10, 31)}})
'''
**************************************************
Extract information relevant to the query:
'''python
information.append({"subject": "Joachim Löw", "relation": "coach of", "object": None, "time": {"start": datetime(1997, 1, 1), "end": datetime(1997, 8, 31)}})
'''
...
```

# Evaluation
Set the `file_path` in `calc_metrics_with_check_and_match.py` and execute it.

# How to Generalize to Other Constrained-based Reasoning QA
In this work, we focus on the time-constrained QA. However, our framework can be modified to generalize to other constrained-based QA tasks. The key is to define the constraint as a python class, which should be able to be measured how well the constraint is satisfied and redefine the `match` function in `calc_metrics_with_check_and_match.py`.

# Note
We run all the experiments with `gpt-3.5-turbo-0301`. However, we found the updated versions like `gpt-3.5-turbo-0613` and `gpt-3.5-turbo-1106` have a different behavior, their in-context learning ability become degraded and cannot correctly perform the task.

# Citation
Please cite the paper and star this repo if you find QAaP interesting or useful, thank you! Feel free to contact zhuxy21@mails.tsinghua.edu.cn or open an issue if you have any questions.
```bibtex
@article{zhu2023qaap,
  title={Question Answering as Programming for Solving Time-Sensitive Questions},
  author={Zhu, Xinyu and Yang, Cheng and Chen, Bei and Li, Siheng and Lou, Jian-Guang and Yang, Yujiu},
  journal={arXiv preprint arXiv:2305.14221},
  year={2023}
}
```
