import sys
import os
import time

import xml.etree.ElementTree as ET

from urllib.request import urlopen
from tabulate import tabulate


class Timings:
    def __init__(self, timing_dict, stage_name):
        self._timing_dict = timing_dict
        self._stage_name = stage_name
        self._oper_time = None
        self._proc_time = None

    def __enter__(self):
        self._oper_time = time.perf_counter()
        self._proc_time = time.process_time()

    def __exit__(self, *args, **kwargs):
        stage_timing = self._timing_dict.get(self._stage_name)
        if stage_timing is None:
            oper_time_tot = round(time.perf_counter() - self._oper_time, 4)
            proc_time_tot = round(time.process_time() - self._proc_time, 4)
            self._timing_dict[self._stage_name] = [oper_time_tot, proc_time_tot]


def load_root_from_url(inc_url, debug_flag):
    """
    Function creates root object of Element class from given URL:

    - urlopen to get data and load it to file OR read file if exists
    - create root object of Element class based on incoming XML
    - set top shop tag as the root tag

    :param inc_url: String
    :param debug_flag: String Y/N
    :return: root: xml.etree.ElementTree.Element
    """

    # optional write to file, for the sake of faster debug
    if debug_flag == 'Y':
        file = os.path.join(os.path.dirname(__file__), "../resources/example.xml")
        if not os.path.isfile(file):
            response = urlopen(inc_url)
            data = response.read()
            text = data.decode('utf-8')
            with open(file, 'w', encoding="utf-8") as f:
                f.write(text)
        else:
            with open(file, 'r', encoding="utf-8") as f:
                text = f.read()
    else:
        response = urlopen(inc_url)
        data = response.read()
        text = data.decode('utf-8')

    try:
        root = ET.fromstring(text)
    except ET.ParseError:
        print('Can\'t parse XML from the input URL')
        return None

    # we need to parse only shop tag, as it contains categories and offers, required for our task
    if root.tag != 'shop':
        for node in root.iter('shop'):
            root = node
            break

    return root


def build_nested_dict(cat_dict, res_dict):
    """
    Build nested dictionary from two given dictionaries

    - recursively replace each id which is a parent with its children

    :param cat_dict: dict with all relations of parent-child
    :param res_dict: nested dict with tree-like relations of parent-child
    :return: res_dict - nested tree-like dict
    """
    for cat_key, cat_value in cat_dict.items():
        for res_key, res_value in res_dict.items():
            # replace each parent id with children list, recursively
            res_value = [build_nested_dict(cat_dict, dict({cat_key: cat_value}))
                         if x == cat_key else x for x in res_value]
            res_dict[res_key] = res_value
    return res_dict


def get_full_cat_descr(res_dict, full_descr_dict, descr_dict, prefix):
    """
    For each id set a full category description based on provided nested dict with relations:

    - For each key:value pair recursively build a full category description

    :param res_dict: nested dict with parent-children relations
    :param full_descr_dict: result dictionary with mapping of ids to full category names
    :param descr_dict: dictionary with mappings of description text to ids
    :param prefix: string prefix, which is used during the recursive build of the full name
    :return: full_descr_dict - dictionary with mapping of ids to full category names
    """
    for res_key, res_value in res_dict.items():
        # Set a prefix of the top level id
        prefix = (prefix + ' / ' if prefix else '') + (descr_dict.get(res_key) if descr_dict.get(res_key) else '')
        # looping through the text description mapping to set available parent-child descriptions
        for descr_key, descr_value in descr_dict.items():
            # for each level we check if we have any values which are not dictionaries and if given key has full name
            if any(isinstance(x, str) for x in res_value) or not full_descr_dict.get(res_key):
                # if we have found key in list, set full name - prefix + parent descr + element descr
                if descr_key in res_value:
                    full_descr_dict[descr_key] = ((prefix + ' / ' if prefix else '') +
                                                  (descr_value if full_descr_dict.get(descr_key) is None
                                                   else full_descr_dict.get(descr_key)))
                    # remove processed id to skip loop if there are no ids left, only dictionaries
                    res_value.remove(descr_key)
                elif descr_key == res_key:
                    # if we have found a description of the key, set full name - prefix or existing value
                    full_descr_dict[descr_key] = (
                        prefix if full_descr_dict.get(descr_key) is None else full_descr_dict.get(descr_key))
            else:
                # break from loop if key has a description and there are no ids left in list
                break
        for i, item in enumerate(res_value):
            # loop through all children elements which are parent for other elements, recursively
            # if element is a dictionary, it means that we have parent-children relation
            if isinstance(item, dict):
                full_descr_dict = get_full_cat_descr(res_value[i], full_descr_dict, descr_dict, prefix)
        # purge prefix before we will set next key:pair to process
        prefix = ''
    return full_descr_dict


def build_output(cat, descr, offers, timings_dict):
    """
    This function is used to build a formatted output from given dictionaries:

    - prepare root level parents dictionary
    - build nested list with dictionaries to have result dict with all elements and dependencies
    - get full description based on result dict
    - return formatted string with mapping of full category names to offers amount

    :param cat: dict - all categories which have children
    :param descr: dict - mapping of category id to text description
    :param offers: dict - mapping of offers amount to category id
    :param timings_dict - timings dictionary for debug
    :return: output: formatted via tabulate string with categories full names and offers amount mapping
    """
    table_list = []
    full_descr_dict = {}
    res_dict = {}

    # build dict with root level parents
    with Timings(timings_dict, 'build root'):
        for cat_key, cat_value in cat.items():
            has_parent = False
            for cat_check_value in cat.values():
                if cat_key in cat_check_value:
                    has_parent = True
                    break
            if not has_parent:
                res_dict[cat_key] = cat_value

    # build nested dict with lists of dictionaries, tree imitation
    with Timings(timings_dict, 'build nested dict'):
        res_dict = build_nested_dict(cat, res_dict)

    prefix = ''
    # build result mapping dict of full category names to ids
    with Timings(timings_dict, 'get full cat descr'):
        full_descr_dict = get_full_cat_descr(res_dict, full_descr_dict, descr, prefix)

    # list of all keys which has description text
    keys = [int(k) for k in descr]

    for key in sorted(keys):
        # [[full category name, offers amount], ...]
        table_list.append([full_descr_dict.get(str(key)),
                           (offers.get(str(key)) if offers.get(str(key)) is not None else 0)])

    # tabulate is used to format the output as a table
    output = tabulate(table_list, headers=["categories", "offers"])

    return output


def main(inc_url, timings_dict, debug_flag):
    """
    Main function:

    - executes other functions
    - parses xml and builds main dicts
    - writes to result file

    :param inc_url: string - incoming url
    :param timings_dict: dict - debug timings dict
    :param debug_flag: string - debug mode Y/N
    """

    # 3 main dictionaries
    # map each parent to children
    categories_dict = {}
    # map id to description
    descr_dict = {}
    # map amount of offers to id
    offers_inclusion_dict = {}

    # load file as a Element class from xml.etree.ElementTree
    with Timings(timings_dict, 'load'):
        root = load_root_from_url(inc_url, debug_flag)

    if not root:
        print('No xml provided, finishing the execution')
        quit()

    # xml parsing
    with Timings(timings_dict, 'parse XML'):
        for child in root:
            # parse categories to build dictionary with all elements which have children ids
            if child.tag == 'categories':
                for categories in child:
                    # {parent_id: [id, id...]}
                    parent_id = categories.attrib.get('parentId')
                    child_id = categories.attrib.get('id')
                    if parent_id:
                        # if category has parent - add id as a child
                        categories_dict[parent_id] = categories_dict.get(parent_id, []) + [child_id]
                        # also add description to the descr_dict
                        descr_dict[child_id] = categories.text
                    else:
                        # if no parent - this id is a parent
                        categories_dict[child_id] = categories_dict.get(child_id, [])
                        # also add description to the descr-dict
                        descr_dict[child_id] = categories.text
            if child.tag == 'offers':
                for offers in child:
                    offer_category_id = offers.find('categoryId').text
                    # map offer amount to id, increment
                    offers_inclusion_dict[offer_category_id] = offers_inclusion_dict.get(offer_category_id, 0) + 1

    # process given 
    with Timings(timings_dict, 'build output'):
        output = build_output(categories_dict, descr_dict, offers_inclusion_dict, timings_dict)

    print(output)

    # write result file in the resources folder
    if debug_flag == 'Y':
        file = os.path.join(os.path.dirname(__file__), "../resources/results.txt")
        with open(file, 'w+', encoding="utf-8") as f:
            f.write(output)

    return


if __name__ == "__main__":
    """
    argv[1] - URL
    argv[2] - debug mode Y/N
    """
    argv = sys.argv
    if len(argv) > 1:
        url = argv[1]
        debug_flag = argv[2] if len(argv) > 2 else 'N'
    else:
        print('URL wasn\'t provided')
        quit()

    timings_dict = {}

    # Timings
    with Timings(timings_dict, 'total'):
        main(url, timings_dict, debug_flag)

    if debug_flag == 'Y':
        print(f'TIMINGS \n{timings_dict}')
