#!/usr/bin/env python3
# -*- coding: utf-8 -*-
def paginate_data(data, page=1, page_size=10):
    """通用分页工具"""
    if page < 1:
        page = 1
    total = len(data)
    total_pages = (total + page_size - 1) // page_size
    start = (page - 1) * page_size
    end = start + page_size
    paginated = data[start:end]
    return {
        "list": paginated,
        "page": page,
        "page_size": page_size,
        "total": total,
        "total_pages": total_pages
    }