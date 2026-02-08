#!/usr/bin/env python3
# -*- coding: utf-8 -*-
def build_tree(data, id_key="id", parent_key="parent_id", children_key="children"):
    """
    构建树形数据结构
    :param data: 扁平列表
    :param id_key: 主键字段名
    :param parent_key: 父级字段名
    :param children_key: 子节点字段名
    :return: 树形列表
    """
    # 构建ID到节点的映射，初始化子节点列表
    node_map = {item[id_key]: {**item, children_key: []} for item in data}
    tree = []

    for item in data:
        parent_id = item[parent_key]
        current_node = node_map[item[id_key]]
        # 根节点（父ID为0/None）加入顶层，否则加入父节点的子列表
        if parent_id == 0 or parent_id is None or parent_id not in node_map:
            tree.append(current_node)
        else:
            node_map[parent_id][children_key].append(current_node)
    
    # 按sort字段排序（通用树形排序）
    def sort_children(node):
        node[children_key].sort(key=lambda x: x.get("sort", 0))
        for child in node[children_key]:
            sort_children(child)
    
    for root in tree:
        sort_children(root)
    return tree