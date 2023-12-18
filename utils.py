import re
import string
from collections import Counter
from unidecode import unidecode
import traceback
import coloredlogs, logging
import datetime as dt
from datetime import datetime
logger = logging.getLogger(__name__)
coloredlogs.install(level='DEBUG', logger=logger)


def create_context_slices(context, max_length=512, stride=384):
    """
    Splits a context into slices of length max_length, with a stride of stride.
    """
    context_paras = context.split("\n")
    context_tokens = []
    slices = []
    for i, para in enumerate(context_paras):
        context_tokens += para.split(" ")
        context_tokens.append("\n")
    while len(context_tokens) > max_length:
        slices.append(" ".join(context_tokens[:max_length]))
        context_tokens = context_tokens[stride:]
    slices.append(" ".join(context_tokens))

    return slices


def extract_answer(answer_key, information):
    if information[0] != "":
        answer_infor = information[0]  # only keep the first one
        if answer_infor[answer_key] is not None:
            if isinstance(answer_infor[answer_key], (list, tuple, frozenset)) and isinstance(answer_infor[answer_key][0], str):
                predictions = list(answer_infor[answer_key])
            elif isinstance(answer_infor[answer_key], (list, tuple, frozenset)) and isinstance(answer_infor[answer_key][0], dict):
                predictions = list(answer_infor[answer_key][0].values())
            elif isinstance(answer_infor[answer_key], dict):
                predictions = list(answer_infor[answer_key].values())
            else:
                predictions = [answer_infor[answer_key]]
        else:
            predictions = [""]
    else:
        predictions = [""]

    assert isinstance(predictions, list), predictions    

    return predictions


def extract_code_from_string(string):
    # Written by chatgpt
    pattern = r"```python(.*?)```"
    matches = re.findall(pattern, string, re.DOTALL)
    if matches:
        return "\n".join(matches)

    return None


def clean_str(p):
    p = unidecode(p)
    try:
        p = p.encode().decode("unicode-escape").encode("latin1").decode("utf-8")
    except:
        p = p.encode().decode("ISO-8859-1").encode("latin1").decode("utf-8")
    # p = re.sub('([a-zA-Z])([.,!?()])', r'\1\2 ', p)
    # p = re.sub('\s{2,}', ' ', p)
    p = re.sub(r'([a-zA-Z])([,.!?()])', r'\1 \2', p)
    p = re.sub(r'([,.!?()])([a-zA-Z])', r'\1 \2', p)

    return p


def f1_score(prediction, ground_truth):
    ZERO_METRIC = (0, 0, 0)

    if prediction in ['yes', 'no', 'noanswer'] and prediction != ground_truth:
        return ZERO_METRIC
    if ground_truth in ['yes', 'no', 'noanswer'] and prediction != ground_truth:
        return ZERO_METRIC

    prediction_tokens = prediction.split()
    ground_truth_tokens = ground_truth.split()
    common = Counter(prediction_tokens) & Counter(ground_truth_tokens)
    num_same = sum(common.values())
    if num_same == 0:
        return ZERO_METRIC
    precision = 1.0 * num_same / len(prediction_tokens)
    recall = 1.0 * num_same / len(ground_truth_tokens)
    f1 = (2 * precision * recall) / (precision + recall)

    return f1, precision, recall


def normalize_answer(s):
    def remove_articles(text):
        return re.sub(r"\b(a|an|the)\b", " ", text)

    def white_space_fix(text):
        return " ".join(text.split())

    def replace_dash_with_space(text):
        return " ".join(text.split("-"))

    def remove_punc(text):
        exclude = set(string.punctuation)
        return "".join([ch for ch in text if ch not in exclude])

    def lower(text):
        if isinstance(text, int) or isinstance(text, float):
            text = str(text)
        return unidecode(text.lower())

    return white_space_fix(remove_articles(remove_punc(replace_dash_with_space(lower(s)))))


def get_metrics(preds, gt_answer):
    if isinstance(gt_answer, str):
        gt_answer = [gt_answer]
    if isinstance(preds, str):
        preds = [preds]
    if len(preds) == 0 and len(gt_answer) != 0:
        return {'reward': 0, 'em': 0, 'f1': 0}
    if len(preds) != 0 and len(gt_answer) == 0:
        return {'reward': 0, 'em': 0, 'f1': 0}
    em = 0
    f1 = 0
    for pred in preds:
        pred = normalize_answer(pred)
        if pred == "":
            if gt_answer[0] == "":
                return {'reward': 1, 'em': 1, 'f1': 1.}
            else:
                return {'reward': 0, 'em': 0, 'f1': 0}
        for gt in gt_answer:
            gt = normalize_answer(gt)
            em = max(em, int(pred == gt))
            f1 = max(f1, f1_score(pred, gt)[0])
            if em:
                return {'reward': 1, 'em': 1, 'f1': 1.}

    return {'reward': em, 'em': em, 'f1': f1}


def calc_time_iou(code):
    time_type = None
    locals_ = {'information': []}
    try:
        exec(code[0], globals(), locals_)
        query = locals_.get('query')
        answer_key = locals_.get('answer_key')
    except Exception as e:
        logger.error("Failed to get origin query")
        query = None
        answer_key = None

    for c in code[1:]:
        try:
            exec(c, globals(), locals_)
        except Exception as e:
            logger.error(f'Failed to execute code:\n{c}')
            print("Error Type:", type(e))
            print("Error Message:", e)
            print(f"Traceback:\n{traceback.format_exc()}")
            continue
    default_start = datetime(1, 1, 1)
    default_end = datetime(3000, 1, 1)
    # query = locals_.get('query')
    information = locals_.get('information')
    if query is None:
        return "object", information
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

    information = [x for x in information if 'subject' in x and 'object' in x and 'relation' in x and x[answer_key] is not None] #and x['time'] is not None]
    if len(information) == 0:
        return "object", [""]

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
            print("Error Message:", e)
            print(f"Traceback:\n{traceback.format_exc()}")
            print(ex)

    overlapped = False
    information = [x for x in information if x['time'] is not None]
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

    return answer_key, information