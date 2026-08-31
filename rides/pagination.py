"""Pagination configuration for list endpoints."""
from rest_framework.pagination import PageNumberPagination


class RidePagination(PageNumberPagination):
    """Page-number pagination with a client-adjustable page size.

    Page-number pagination keeps sorting predictable: the ORDER BY plus
    LIMIT/OFFSET is pushed down to the database, so pagination continues to
    work whether we sort by ``pickup_time`` or by distance.
    """

    page_size = 10
    page_size_query_param = "page_size"
    max_page_size = 100
