ghcprofview README
==================

GHC `.prof` files viewer, implemented in Python + Qt5. Synopsis:

    ./ghcprofview.py path/to/file.prof

* In addition to information provided by GHC, there are two columns:
  * Time Relative: share of "Time Inherited" of this item with relation to it's
    parent item. For example, if this item has "Time Inherited" 20%, and it's
    parent has "Time Inherited" 30%, then "Time Relative" is 20% / 30% =
    66.66%.
  * Alloc Relative: same, but about "Alloc Inherited".
* Click on column header to sort by that column.
* Right-click on table header to select which columns to display.
* Double-click at the edge of column header to adjust column width automatically.
* Use Search button to search function by name.
* Use filters to display interesting records only. Filtering is performed based
  on combination of fields: Name, Time Individual, Alloc Individual, Time
  Inherited, Alloc Inherited.

See also `ghcprofview` implementation in Haskell - [ghcprofview-hs][1].

[1]: https://github.com/portnov/ghcprofview-hs

![Screenshot](https://user-images.githubusercontent.com/284644/61595379-e4863b80-ac0f-11e9-9263-01e54211fedc.png)

