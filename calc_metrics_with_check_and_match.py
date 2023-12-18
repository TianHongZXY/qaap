import random
import jsonlines
from typing import List, Dict
from datetime import datetime, timedelta
import datetime as dt
from utils import extract_answer, get_metrics, extract_code_from_string, normalize_answer


def match(query, information, answer_key):
    time_type = None
    default_start = datetime(1, 1, 1)
    default_end = datetime(3000, 1, 1)
    if "time" not in query or query['time'] is None or (("start" in query['time'] and "end" in query['time']) and (query['time']['start'] is None and query['time']['end'] is None)):
        query['time'] = {'start': default_start, 'end': default_end}
        time_type = 'overlap'
    elif isinstance(query['time'], datetime):
        query['time'] = {'start': query['time'], 'end': query['time'] + dt.timedelta(365)}
        time_type = 'overlap'
    elif 'start' not in query['time'] or query['time']['start'] is None:
        time_type = 'before or end'
    elif 'end' not in query['time'] or query['time']['end'] is None:
        time_type = 'after or start'
    else:
        time_type = 'overlap'

    information = [x for x in information if 'subject' in x and 'object' in x and 'relation' in x] #and x['time'] is not None]
    information = [x for x in information if x[answer_key] is not None]
    if len(information) == 0:
        return [""]

    for idx, ex in enumerate(information):
        try:
            if "time" not in ex or ex['time'] is None or (("start" in ex['time'] and "end" in ex['time']) and (ex['time']['start'] is None and ex['time']['end'] is None)):
                ex['time'] = {'start': default_start, 'end': default_end}
            elif isinstance(ex['time'], datetime):
                ex['time'] = {'start': ex['time'], 'end': ex['time'] + dt.timedelta(365)}
            elif len(ex['time']) == 0:
                ex['time'] = {'start': default_start, 'end': default_end}
            if 'start' not in ex['time'] or ex['time']['start'] is None:
                ex['time'].update(start=default_start) 
            if 'end' not in ex['time'] or ex['time']['end'] is None:
                ex['time'].update(end=default_end)
        except Exception as e:
            print("Error Type:", type(e))

    overlapped = False
    information = [x for x in information if x['time'] is not None]
    # answer_count = defaultdict(int)
    if time_type == "overlap":
        for idx, ex in enumerate(information):
            latest_start = max(query['time']['start'], ex['time']['start'])
            earliest_end = min(query['time']['end'], ex['time']['end'])
            delta = (earliest_end - latest_start).days + 1
            overlap = max(0, delta)
            if overlap > 0:
                overlapped = True
            time_union = max((query['time']['end'] - query['time']['start']).days + (ex['time']['end'] - ex['time']['start']).days  - overlap, 1)
            ex.update(overlap=overlap)
            ex.update(time_union=time_union)
            ex.update(time_iou=overlap / time_union)
        information = sorted(information, key=lambda x: (x['time_iou'], x['overlap']), reverse=True)
    elif time_type == "after or start":
        information = sorted(information, key=lambda x: abs((x['time']['start'] - query['time']['start']).days))
    elif time_type == "before or end":
        information = sorted(information, key=lambda x: abs((x['time']['end'] - query['time']['end']).days))

    return information


def calc_origin_metrics(data):
    rs = []
    f1_list = []
    for ex in data:
        gt_answer = ex['gt_answer']
        answer = ex['answer']
        metrics = get_metrics(answer, gt_answer)
        rs.append(metrics['em'])
        f1_list.append(metrics['f1'])
    em_num = sum(rs)
    em_rate = sum(rs) / len(rs)
    avg_f1 = sum(f1_list) / len(f1_list)
    print(f"em number: {em_num}, em rate: {em_rate}, avg f1: {avg_f1:.5f}")


def calc_metrics(data):
    rs = []
    f1_list = []
    for idx, ex in enumerate(data):
        traj_list = ex['traj_list']
        parsed_query = traj_list[0]
        parsed_query = extract_code_from_string(parsed_query)
        query_ = {}
        try:
            exec(parsed_query, globals(), query_) 
            query = query_['query']
            answer_key = query_['answer_key']
        except Exception as e:
            print(f"fail to get query:\n{parsed_query}")
            rs.append(0)
            f1_list.append(0)
            continue

        context_slices = ex['context_slices']
        information_list = ex['information_list']
        final_information_list = []
        assert len(context_slices) == len(information_list)
        if len(context_slices) == 0:
            print(f"{idx} no context, Q: {ex['question']}")
            rs.append(0)
            f1_list.append(0)
            continue

        cot_context = context_slices[0]
        cot_infor = information_list[0]
        cot_instances = []
        locals_ = {'information': []}
        try:
            cot_infor = extract_code_from_string(cot_infor)
            if cot_infor is not None:
                for line in cot_infor.split("\n"):
                    try:
                        exec(line, globals(), locals_)
                    except Exception as e:
                        continue
        except Exception as e:
            print(f"fail to execute code:\n{cot_infor}")

        if CHECK_TIME:
            for ins in locals_['information']:
                if 'time' not in ins or ins['time'] is None:
                    cot_instances.append(ins)
                    continue
                if 'start' in ins['time'] and ins['time']['start'] is not None:
                    try:
                        if str(ins['time']['start'].year) not in cot_context:
                            ins['time']['start'] = None
                    except Exception as e:
                        pass
                if 'end' in ins['time'] and ins['time']['end'] is not None:
                    try:
                        if str(ins['time']['end'].year) not in cot_context:
                            ins['time']['end'] = None
                    except Exception as e:
                        pass
                cot_instances.append(ins)
        else:
            cot_instances = locals_['information']

        extract_instances = []
        for text, infor in zip(context_slices[1:], information_list[1:]):
            if not infor:
                continue
            locals_ = {'information': []}
            try:
                infor = extract_code_from_string(infor)
                if infor is not None:
                    for line in infor.split("\n"):
                        try:
                            exec(line, globals(), locals_)
                        except Exception as e:
                            continue
            except Exception as e:
                print(f"fail to execute code:\n{infor}")
                continue
            if CHECK_TIME:
                for ins in locals_['information']:
                    if 'time' not in ins or ins['time'] is None:
                        extract_instances.append(ins)
                        continue
                    if 'start' in ins['time'] and ins['time']['start'] is not None:
                        try:
                            if str(ins['time']['start'].year) not in text:
                                ins['time']['start'] = None
                        except Exception as e:
                            pass
                    elif 'end' in ins['time'] and ins['time']['end'] is not None:
                        try:
                            if str(ins['time']['end'].year) not in text:
                                ins['time']['end'] = None
                        except Exception as e:
                            pass
                    extract_instances.append(ins)
            else:
                extract_instances.extend(locals_['information'])

        if CHECK_APPEAR:
            try:
                possible_answer_from_extract = [normalize_answer(ins_e[answer_key]) for ins_e in extract_instances if answer_key in ins_e and isinstance(ins_e[answer_key], str)]
                if len(possible_answer_from_extract) != 0:
                    for ins_c in cot_instances:
                        if answer_key not in ins_c or ins_c[answer_key] is None:
                            # print("No answer key ins_c", answer_key, ins_c)
                            continue
                        if normalize_answer(ins_c[answer_key]) in possible_answer_from_extract:
                            final_information_list.append(ins_c)
                else:
                    final_information_list += cot_instances
                final_information_list += extract_instances
            except Exception as e:
                final_information_list = cot_instances + extract_instances
        else:
            final_information_list = cot_instances + extract_instances

        for idy, ey in enumerate(final_information_list):
            if 'subject' not in query or 'object' not in query or 'subject' not in ey or 'object' not in ey:
                continue
            if ey[answer_key] == query['subject'] or ey[answer_key] == query['object']:
                if answer_key == "subject":
                    final_information_list[idy][answer_key] = final_information_list[idy]['object']
                else:
                    final_information_list[idy][answer_key] = final_information_list[idy]['subject']

        # Match
        try:
            final_information_list = match(query, final_information_list, answer_key)
        except Exception as e:
            pass
        try:
            answer = extract_answer(answer_key, final_information_list)
        except Exception as e:
            answer = [""]

        gt_answer = ex['gt_answer']
        metrics = get_metrics(answer, gt_answer)

        rs.append(metrics['em'])
        f1_list.append(metrics['f1'])

    em_num = sum(rs)
    em_rate = sum(rs) / len(rs)
    avg_f1 = sum(f1_list) / len(f1_list)
    print(f"em number: {em_num}, em rate: {em_rate}, avg f1: {avg_f1:.5f}")


if __name__ == "__main__":
    CHECK_TIME = True
    CHECK_APPEAR = True
    file_path = "outputs/<your_result_file>"
    with jsonlines.open(file_path, "r") as f:
        data = list(f)
        random.seed(0)
        random.shuffle(data)
        print("data size: ", len(data))

    print("metrics")
    calc_metrics(data)
