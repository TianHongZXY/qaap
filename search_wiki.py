# ====================================================
#   Copyright (C) 2023  All rights reserved.
#
#   Author        : Xinyu Zhu
#   Email         : zhuxy21@mails.tsinghua.edu.cn
#   File Name     : search_wiki.py
#   Last Modified : 2023-01-30 20:09
#   Describe      : 
#
# ====================================================
import re
import time
import requests
import wikipedia
from bs4 import BeautifulSoup
from utils import clean_str
from unidecode import unidecode
import pandas as pd
wikipedia.set_lang("en")


def extract_info_table(soup):
    try:
        tags = soup.select_one(".mw-parser-output").find_all(recursive=False)
        tables = soup.find_all('table', {'class': 'infobox'})
        if len(tables) == 0:
            tables = soup.find_all('table', {'class': 'infobox vcard'})
        if len(tables) == 0:
            tables = soup.find_all('table', {'class': 'infobox vcard plainlist'})
        if len(tables) == 0:
            tables = soup.find_all('table', {'class': 'infobox vevent'})
        if len(tables) == 0:
            tables = soup.find_all('table', {'class': 'infobox biography vcard'})
        if len(tables) == 0:
            return ""
    except Exception as e:
        return ""

    rh_list = []
    rl_list = []
    rd_list = []
    flat_table = ""
    for table in tables:
        for row in table.find_all('tr'):
            if len(row) == 0:
                continue
            row_head = row.find_all('th', {'class': 'infobox-header'})
            row_label = row.find_all('th', {'class': 'infobox-label'})
            row_data = row.find_all('td', {'class': 'infobox-data'})
            for rh in row_head:
                if rh.text.strip() == "":
                    continue
                flat_table += "\nTitle: " + rh.text.replace('\n', ' ')
            if len(row_label) > 0:
                flat_table += " | "
            for rl in row_label:
                if rl.text.strip() == "":
                    continue
                flat_table += rl.text.replace('\n', ' ') + " | "
            for rd in row_data:
                if rd.text.strip() == "":
                    continue
                flat_table += rd.text.replace('\n', ' ') + " | "
            flat_table = flat_table.strip()
            flat_table += "\n"
        flat_table = flat_table.strip() + "\n"
        # print(flat_table)

    return unidecode(flat_table)


def extract_wiki_table(soup):
    try:
        tags = soup.select_one(".mw-parser-output").find_all(recursive=False)
        tables = soup.find_all('table', {'class': 'wikitable'})
    except Exception as e:
        return []
    if len(tables) == 0:
        return []

    results = []
    pd_failed_tables = []
    for t in tables:
        try:
            df = pd.read_html(str(t))
        except Exception as e:
            pd_failed_tables.append(t)
            continue
        x = df[0].to_markdown()
        x = re.sub(' +', ' ', x)
        x = x.split("\n")
        x.pop(1)
        results.append("\n".join(x))

    if len(pd_failed_tables) == 0:
        return results

    # current using pandas to read the table instead of the code below
    for table in pd_failed_tables:
        rh_list = []
        rl_list = []
        rd_list = []
        flat_table = ""
        for row in table.find_all('tr'):
            if len(row) == 0:
                continue
            row_head = row.find_all('th')
            row_label = row.find_all('th')
            row_data = row.find_all('td')
            for rh in row_head:
                if rh.text.strip() == "":
                    continue
                flat_table += "\n" + rh.text.replace('\n', ' ')
            if len(row_label) > 0:
                flat_table += " | "
            for rl in row_label:
                if rl.text.strip() == "":
                    continue
                flat_table += rl.text.replace('\n', ' ') + " | "
            for rd in row_data:
                if rd.text.strip() == "":
                    continue
                flat_table += rd.text.replace('\n', ' ') + " | "
            flat_table = flat_table.strip()
            flat_table += "\n"
        flat_table = flat_table.strip() + "\n"
        results.append(unidecode(flat_table))
        # print(flat_table)

    return results


def search(entity, summary=True):
    entity_ = entity.replace(" ", "+")
    search_url = f"https://en.wikipedia.org/w/index.php?search={entity_}"
    try:
        response_text = requests.get(search_url).text
        soup = BeautifulSoup(response_text, features="html.parser")
    except requests.exceptions.ProxyError:
        time.sleep(2)
        response_text = requests.get(search_url).text
        soup = BeautifulSoup(response_text, features="html.parser")
    try:
        result_divs = soup.find_all("div", {"class": "mw-search-result-heading"})
        if result_divs:  # mismatch
            result_titles = [div.get_text().strip() for div in result_divs]
            for i in range(len(result_titles)):
                result_titles[i] = result_titles[i].split(" ( redirect from ")[0]
                result_titles[i] = result_titles[i].split(" (redirect from ")[0]
            
            results = [x for x in result_titles if x.lower() != entity.lower() and x.lower() != entity[1:-1].lower()][:5]
            return False, results
        paragraphs = []
        for p in soup.find_all("p") + soup.find_all("ul"):
            p = p.get_text().strip()
            if len(p.split()) > 2:
                p = re.sub(' +', ' ', p)
                p = re.sub(r'[\n]+', '\n', p)
                paragraphs.append(clean_str(p) + "\n")
        if any("may refer to" in p for p in paragraphs):
            return search("[" + entity + "]", summary)
        page = wikipedia.page(entity)
        if summary:
            main_text = page.summary
        else:
            main_text = page.content
        paragraphs = []
        for p in soup.find_all("p") + soup.find_all("ul"):
            p = p.get_text().strip()
            if len(p.split()) > 2:
                p = re.sub(' +', ' ', p)
                p = re.sub(r'[\n]+', '\n', p)
                paragraphs.append(clean_str(p) + "\n")
        if any("may refer to:" in p for p in paragraphs):
            return search("[" + entity + "]")
    except wikipedia.exceptions.DisambiguationError as e:
        main_text = ""
        #NOTE if summary add exintro parameter
        if summary:
            r = requests.get(f"https://en.wikipedia.org/w/api.php?action=query&explaintext=&exsectionformat=plain&prop=extracts&exintro&redirects=&titles={entity}&format=json")
        else:
            r = requests.get(f"https://en.wikipedia.org/w/api.php?action=query&explaintext=&exsectionformat=plain&prop=extracts&redirects=&titles={entity}&format=json")
        x = r.json()
        extract = []
        pages = x['query']['pages']
        for key, val in pages.items():
            if 'extract' not in val:
                return False, e.options[:5]
            main_text += val['extract']
    except wikipedia.exceptions.PageError:
        try:
            script_content = soup.select_one("head > script:nth-of-type(1)").decode_contents()
            page_id = re.search(r".*wgArticleId..([0-9]+).*",script_content).group(1)
            page = wikipedia.page(pageid=page_id)
            if summary:
                main_text = page.summary
            else:
                main_text = page.content
        except Exception as e:
            return search(entity)
    except wikipedia.exceptions.WikipediaException:
        time.sleep(1)
        return search(entity, summary)
    except Exception as e:
        return search(entity)

    main_text = main_text.split("== References ==")[0]
    main_text = main_text.split("== See also ==")[0]
    main_text = [main_text]
    for sup in soup.find_all("sup", {'class':'reference'}):  # delete all reference like [1][3][13]
        sup.decompose()
    info_table = extract_info_table(soup)
    wiki_tables = extract_wiki_table(soup)
    tables = [info_table] + wiki_tables

    return True, (tables, main_text)
