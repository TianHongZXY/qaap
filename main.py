import os
import time
import json
import random
import argparse
import jsonlines
import openai
import tiktoken
import datetime as dt
from datetime import datetime, timedelta
import coloredlogs, logging
import traceback
from search_wiki import search
from utils import create_context_slices, extract_answer, get_metrics, extract_code_from_string, calc_time_iou
logger = logging.getLogger(__name__)
coloredlogs.install(level='DEBUG', logger=logger)


def post(prompt, stop, max_tokens=1600, model_name="gpt-3.5-turbo"):
    global TOKENIZER
    prompt_num_tokens = len(TOKENIZER.encode(prompt))
    if prompt_num_tokens >= 4096:
        return ""
    params = {
        'max_tokens': min(4097 - prompt_num_tokens, max_tokens),
        'temperature': 0.0,
        'top_p': 1,
        'n': 1,
        'stop': stop,
    }
    if model_name == "gpt-3.5-turbo":
        params["messages"] = [
            {"role": "system", "content": "You are a helpful assistant."},
            {"role": "user", "content": prompt}
        ]
    else:
        params["prompt"] = prompt

    res = None
    attempts = 0
    max_attempts = 3
    while res is None and attempts < max_attempts:
        try:
            if model_name == "gpt-3.5-turbo":
                response = openai.ChatCompletion.create(
                    engine=model_name,
                    **params, 
                    timeout=60
                )
                res = response.choices[0].message["content"]
            else:
                response = openai.Completion.create(
                    engine=model_name,
                    **params,
                    timeout=60
                )
                res = response['choices'][0]['text']
        except openai.error.InvalidRequestError as e:
            print(e)
            print(f"Traceback:\n{traceback.format_exc()}")
            return ""
        except Exception as e:
            print(e)
            print(f"Traceback:\n{traceback.format_exc()}")
            attempts += 1
            time.sleep(1)
            continue

    if res is None:
        return ""

    return res


def qaap(init_prompt, question, info, args, passage=None):
    prompt = init_prompt + "\n\nQuestion:" + question + "\nQuestion parsing:\n"
    # parse
    parsed_query = post(prompt, stop=["\nSearch:"], max_tokens=200, model_name=args.model_name)
    print(parsed_query)
    time.sleep(1)
    info['traj_list'].append(parsed_query)
    info['context_slices'] = []
    query = extract_code_from_string(parsed_query)

    prompt += parsed_query
    extracted_code_list = [query]

    # search
    parsed_search = post(prompt + '\nSearch:\n', stop=['\nGenerate'], max_tokens=200, model_name=args.model_name)
    parsed_search = parsed_search.split("Failed entities")[0]
    parsed_search = parsed_search.split("\nContext")[0]
    print('Search:\n' + parsed_search)
    info['traj_list'].append(parsed_search)
    prompt += parsed_search
    locals_ = {}
    tables_list = []
    passages_list = []
    if passage is None:
        # retrieve passage from wikipedia
        try:
            exec(extract_code_from_string(parsed_search), globals(), locals_)
        except Exception as e:
            print(e)
            logger.error('Failed to obtain search entities.')
        
        try:
            entities_to_search = locals_['entities_to_search']
        except KeyError:
            entities_to_search = []
            info['search_failed'] = True
        
        for et_idx, et in enumerate(entities_to_search):
            state, results = search(et, summary=args.return_search_passage == "summary")
            while not state:
                locals_temp = {}
                f_et = [et]
                new_search_str =  \
    f"""\nFailed entities:
    ```python
    failed_entities = {f_et}
    similar_entities = {results}
    ```
    """
                info['traj_list'].append(new_search_str)
                print(new_search_str)
                parsed_search = post(prompt + new_search_str + '\nSearch:\n', stop=['\nGenerate'], max_tokens=200, model_name=args.model_name)
                parsed_search = parsed_search.split("Failed entities")[0]
                parsed_search = parsed_search.split("\nContext")[0]
                print(f'\nSearch:\n{parsed_search}')
                info['traj_list'].append(parsed_search)
                try:
                    exec(extract_code_from_string(parsed_search), globals(), locals_temp)
                except Exception as e:
                    print(e)
                    logger.error('Failed to obtain search entities.')
                    info['search_failed'] = True
                    break
                    # return [""], info
                et_to_search = locals_temp['entities_to_search']
                # state, results = search(et_to_search[0])
                state, results = search(et_to_search[0], summary=args.return_search_passage == "summary")
                if state == False:
                    info['search_failed'] = True
                    break
                    # return [""], info
            tables = results[0]
            passages = results[1]
            tables_list.append(tables)
            passages_list.append(passages)
    else:
        tables_list = [[]]
        passages_list = [[passage]]

    generated_document = post(prompt + "\nGenerate a background document from Wikipedia to answer the given question:", stop=["\nExtract"], max_tokens=200, model_name=args.model_name)
    info['context_slices'].append(generated_document)
    res = post(prompt + "\nGenerate a background document from Wikipedia to answer the given question:" + generated_document + '\nExtract information relevant to the query:\n', max_tokens=400, stop=['\nContext'], model_name=args.model_name)
    res = res.split("\nContext")[0]
    res = res.split("\nQuestion")[0]
    res = res.split("\nSearch")[0]
    info['information_list'].append(res)
    print("-" * 50)
    # print(context_slice)
    print("\nGenerate a background document from Wikipedia to answer the given question:" + generated_document + '\nExtract information relevant to the query:\n' + res)
    info['traj_list'].append("\nGenerate a background document from Wikipedia to answer the given question:" + generated_document + '\nExtract information relevant to the query:\n' + res)
    try:
        extracted_code = extract_code_from_string(res)
        if extracted_code is not None:
            for c in extracted_code.split("\n"):
                if c:
                    if "query" in c or "information = " in c:
                            continue
                    extracted_code_list.append(c)
    except Exception as e:
        logger.error('Failed to obtain code from returned strings.')
        print("Error Type:", type(e))
        print("Error Message:", e)
        print(f"Traceback:\n{traceback.format_exc()}")

    for tables, passage_list in zip(tables_list, passages_list):
        table_slices = []
        for t in tables:
            table_slices += create_context_slices(t)
        context_slices = create_context_slices("\n".join(passage_list))

        for context_slice in table_slices + context_slices:
            info['context_slices'].append(context_slice)
            res = post(prompt + "\nContext: " + context_slice + '\nExtract information relevant to the query:\n', stop=['\n\nQuestion:'], model_name=args.model_name)
            res = res.split("\nContext:")[0]
            res = res.split("\nSearch:")[0]
            info['information_list'].append(res)
            print("*" * 50)
            # print(context_slice)
            print('Extract information relevant to the query:\n' + res)
            info['traj_list'].append("Extract information relevant to the query:\n" + res)
            try:
                extracted_code = extract_code_from_string(res)
                if extracted_code is not None:
                    for c in extracted_code.split("\n"):
                        if c:
                            if "query" in c or "information = " in c:
                                    continue
                            extracted_code_list.append(c)
                    # extracted_code_list.append(extracted_code)
            except Exception as e:
                logger.error('Failed to obtain code from returned strings.')
                print("Error Type:", type(e))
                print("Error Message:", e)
                print(f"Traceback:\n{traceback.format_exc()}")
                continue
    try:
        answer_key, information = calc_time_iou(extracted_code_list)
        predictions = extract_answer(answer_key, information)
    except Exception as e:
        logger.error('Failed to obtain answer after code execution.')
        print("Error Type:", type(e))
        print("Error Message:", e)
        print(f"Traceback:\n{traceback.format_exc()}")
        predictions = [""]
    
    assert len(info['information_list']) == len(info['context_slices'])

    return predictions, info


if __name__ == "__main__":
    TIMESTAMP = time.strftime('%Y-%m-%d_%H-%M-%S', time.localtime())
    parser = argparse.ArgumentParser()
    parser.add_argument("--prompt_file", type=str)
    parser.add_argument("--given_context", type=int, choices=[0, 1])
    parser.add_argument("--model_name", default="gpt-3.5-turbo")
    parser.add_argument("--dataset", type=str, choices=["timeqa", "timequestions", "tempquestions"])
    parser.add_argument("--data_file", type=str)
    parser.add_argument("--resume_id", type=int, default=-1)
    parser.add_argument("--max_slice_length", type=int, default=512)
    parser.add_argument("--slice_stride", type=int, default=384)
    parser.add_argument("--return_search_passage", type=str, default="content")
    parser.add_argument("--comment", type=str, default="")
    args = parser.parse_args()
    ROOT_DIR = "~/qaap"
    DATA_DIR = os.path.join(ROOT_DIR, "data")
    PROMPT_DIR = os.path.join(ROOT_DIR, 'prompts')
    TOKENIZER = tiktoken.encoding_for_model(args.model_name)

    openai.api_key = ""

    prompt_file = os.path.join(PROMPT_DIR, args.prompt_file)
    with open(prompt_file, 'r', encoding="utf-8") as f:
        prompt_dict = json.load(f)
        init_prompt = prompt_dict['prompt_text']

    with jsonlines.open(f"{DATA_DIR}/{args.dataset}/{args.data_file}") as f:
        data = list(f)
    idxs = list(range(len(data)))
    random.seed(0)
    random.shuffle(idxs)
    data = [data[i] for i in idxs[:100]]
    print("Data size: ", len(data))

    rs = []
    f1_list = []
    old_time = time.time()
    with jsonlines.open(f'outputs/{args.dataset}.jsonl-' + args.comment + TIMESTAMP, mode='w', flush=True) as f:
        for idx, ex in enumerate(data):
            if idx < args.resume_id:
                continue
            question = ex['question']
            info = {'question': question, 'gt_answer': ex['answer'], 'answer': None, 'traj_list': [], 'information_list': []}
            print("-" * 50)
            print(idx, question)

            if args.given_context:
                passage = ex['context']
            else:
                passage = None

            predictions, info = qaap(init_prompt, question, info, args, passage)

            info['answer'] = predictions
            print("Predictions: ", predictions)
            print("Ground truth: ", ex['answer'])
            metrics = get_metrics(predictions, ex['answer'])
            info.update(metrics)
            rs.append(metrics['em'])
            f1_list.append(metrics['f1'])
            em_num = sum(rs)
            em_rate = sum(rs) / len(rs)
            avg_f1 = sum(f1_list) / len(f1_list)
            avg_time_per_ques = (time.time() - old_time) / len(rs)
            logger.info(f"idx: {idx}, em number: {em_num}, em rate: {em_rate}, avg f1: {avg_f1:.3f}, avg time per question {avg_time_per_ques:.1f}s.")
            f.write(info)
