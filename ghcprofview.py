#!/usr/bin/env python3

import sys
import re
import traceback

from PyQt5.QtGui import QPainter, QPixmap, QIcon, QStandardItemModel, QStandardItem, QColor
from PyQt5 import QtCore
from PyQt5.QtCore import QRect, QSize, Qt, QObject, QTimer, pyqtSignal, QSettings, QModelIndex, QVariant, QAbstractItemModel, QSortFilterProxyModel, QItemSelectionModel
from PyQt5.QtWidgets import QApplication, QWidget, QToolBar, QMainWindow, \
        QDialog, QVBoxLayout, QHBoxLayout, QAction, QActionGroup, QLabel, QFileDialog, \
        QFrame, QDockWidget, QMessageBox, QListWidget, QListWidgetItem, QMenu, \
        QSpinBox, QComboBox, \
        QTreeView, QLineEdit, QPushButton, QAbstractItemView, QStyle, \
        QStyledItemDelegate, QTabWidget

NAME_COLUMN = 1

column_names = ["No", "Name", "Entries",
                "Time Individual %", "Alloc Individual %",
                "Time Inherited %", "Alloc Inherited %",
                "Time Relative %", "Alloc Relative %",
                "Module", "Source"]

class Record(object):
    def __init__(self, id):
        self.id = id
        self._row = 0
        self.children = []
        self.summands = dict()
        self.parent = None

        self.no = 0
        self.entries = 0
        self.individual_time = 0
        self.individual_alloc = 0

        self._relative_time = None
        self._relative_alloc = None
        self._inherited_time = None
        self._inherited_alloc = None

    @classmethod
    def parse(cls, id, has_src, fields):
        record = Record(id)

        record.name = fields[0]
        record.module = fields[1]
        record.src = fields[2]
        k = 0
        if has_src and record.src == "<no":
            record.src = "<no>"
            k = 2
        elif not has_src:
            record.src = "<no>"
            k = -1
        record.no = int(fields[3+k])
        record.entries = int(fields[4+k])
        record.individual_time = float(fields[5+k])
        record.individual_alloc = float(fields[6+k])
        record._inherited_time = float(fields[7+k])
        record._inherited_alloc = float(fields[8+k])

        return record

    @classmethod
    def new(cls, id, name = None, module = None, src = None, individual_time = None):
        record = Record(id)
        record.no = id
        if name is None:
            name = id
        record.name = name
        record.module = module
        record.src = src
        if individual_time is not None:
            record.individual_time = individual_time
        return record

    @classmethod
    def copy(cls, other, with_children=False):
        record = Record(other.id)
        record.name = other.name
        record.module = other.module
        record.src = other.src
        record.no = other.no
        record.entries = other.entries
        record.individual_time = other.individual_time
        record.individual_alloc = other.individual_alloc
        record._inherited_time = other._inherited_time
        record._inherited_alloc = other._inherited_alloc
        if with_children:
            for child in other.children:
                record.add_child(Record.copy(child, with_children))
        return record

    def has_child_no(self, no):
        return no in [child.no for child in self.children]

    def add_child(self, child):
        child._row = len(self.children)
        child.parent = self
        self.children.append(child)

    def add_children(self, children):
        for child in children:
            self.add_child(child)

    def is_sum(self):
        return self.no == [] or len(self.summands) != 0

    def add(self, other):
        next_id = self.get_max_id([other]) + 1
        result = Record.new(next_id, self.name, self.module, self.src)

        if self.is_sum():
            result.summands = other.summands.copy()
            #print("add (self): {} + {}".format(result.summands, self.summands))
            result.summands.update(self.summands)
        else:
            result.summands[self.no] = self

        if other.is_sum():
            result.summands.update(self.summands.copy())
            #print("add (other): {} + {}".format(result.summands, other.summands))
            result.summands.update(other.summands)
        else:
            if other.no not in result.summands:
                result.summands[other.no] = other

        result.no = tuple(result.summands.keys())

        if len(result.no) == 1 and len(result.summands) == 1:
            return result.summands[result.no[0]]

        children = self.children + other.children
        new_children = []
        for child in children:
            new_child = None
            for existing_child in new_children:
                if existing_child.is_same_function(child):
                    new_child = existing_child.add(child)
                    break

            if new_child is None:
                new_child = child
            new_children.append(new_child)

        result.add_children(new_children)

        return result

    def _flatten(self):
        if not self.is_sum():
            return [self.no], self

        self.individual_time = 0
        self.individual_alloc = 0
        self._inherited_time = 0
        self._inherited_alloc = 0
        self.entries = 0
        #self.children = []

        nos = []
        for no in self.summands:
            n, that = self.summands[no]._flatten()
            self.entries += that.entries
            self.individual_time += that.individual_time
            self.individual_alloc += that.individual_alloc
            self._inherited_time += that.inherited_time
            self._inherited_alloc += that.inherited_alloc
            #self.add_children(that.children)
            nos.extend(n)
        nos = tuple(nos)

        if len(nos) == 1:
            self.no = nos[0]
        else:
            self.no = nos

        self.summands = dict()

        return self.no, self

    def flatten(self):
        for child in self.children:
            child.flatten()
        self._flatten()

    def get_max_id(self, items=None):
        result = self.id
        for child in self.children:
            m = child.get_max_id()
            if m > result:
                result = m
        if items is not None:
            for item in items:
                m = item.get_max_id()
                if m > result:
                    result = m
        return result

    @staticmethod
    def insert(root, path):
        def go(root, path, depth):
            if not path:
                return
            head = path[0]
            rest = path[1:]
            next_child = None
            new_children = []
            for i, child in enumerate(root.children[:]):
                if child.is_same_function(head):
                    new_child = child.add(head)
                    new_children.append(new_child)
                    next_child = new_child
                else:
                    new_children.append(child)

            assert len(new_children) == len(root.children)
            for i, child in enumerate(new_children):
                child._row = i
                child.parent = root
            root.children = new_children

            if next_child is None:
                root.add_child(head)
                next_child = head

            go(next_child, rest, depth+1)

        go(root, path, 0)

    def get_all_paths(self):
        me = Record.copy(self)
        paths = []
        if not self.children:
            return [[me]]
        for child in self.children:
            for child_path in child.get_all_paths():
                paths.append([me] + child_path)
        return paths

    def search_paths(self, needle, with_children=False):
        if self.is_same_function(needle):
            copy = Record.copy(self, with_children)
            return [[copy]]
        paths = []
        for child in self.children:
            for sub_path in child.search_paths(needle, with_children):
                copy = Record.copy(self, with_children)
                paths.append([copy] + sub_path)
        return paths

    def search(self, needle):
        results = []
        if self.is_same_function(needle):
            results.append(self)
        for child in self.children:
            sub_results = child.search(needle)
            results.extend(sub_results)
        return results

    def reverse_tree(self, needle):
        root = Record.new(self.get_max_id()+1, "Root")
        for path in self.search_paths(needle):
            Record.insert(root, list(reversed(path[1:])))
        root.flatten()
        #print_table([root])
        return root

    def forward_tree(self, needle):
        root = Record.new(self.get_max_id()+1, "Root")
        for item in self.search(needle):
            for sub_path in item.get_all_paths():
                Record.insert(root, sub_path)
        root.flatten()
        #print_table([root])
        return root

    def row(self):
        if not self.parent:
            return 0

        return self._row
        #return self.parent.children.index(self)

    @property
    def inherited_time(self):
        if self._inherited_time is None:
            value = self.individual_time
            for child in self.children:
                value += child.inherited_time
            self._inherited_time = value
        return self._inherited_time

    @property
    def inherited_alloc(self):
        if self._inherited_alloc is None:
            value = self.individual_alloc
            for child in self.children:
                value += child.inherited_alloc
            self._inherited_alloc = value
        return self._inherited_alloc

    def _calc_percent(self, parent, value):
        if parent is None:
            return None
        if value > parent:
            value, parent = parent, value
        if parent == 0:
            return None

        return round(100 * value / parent, 2)

    @property
    def relative_time(self):
        if self._relative_time is None:
            self._relative_time = self._calc_percent(self.parent.inherited_time, self.inherited_time)
        return self._relative_time

    @property
    def relative_alloc(self):
        if self._relative_alloc is None:
            self._relative_alloc = self._calc_percent(self.parent.inherited_alloc, self.inherited_alloc)
        return self._relative_alloc

    def is_same_function(self, other):
        return self.name == other.name and \
                self.module == other.module and \
                self.src == other.src

    def data(self, col):
        row = [self.no,
                self.name,
                self.entries,
                self.individual_time,
                self.individual_alloc,
                self.inherited_time,
                self.inherited_alloc,
                self.relative_time,
                self.relative_alloc,
                self.module,
                self.src
            ]
        return row[col]

    def __eq__(self, other):
        return  self.id == other.id and \
                self.no == other.no and \
                self.name == other.name and \
                self.module == other.module and \
                self.src == other.src and \
                self.entries == other.entries

    def __repr__(self):
        return "[{}] {}: {} ({} children)".format(self.no, self.name, self.individual_time, len(self.children))

def get_indent(s):
    count = 0
    for c in s:
        if c == ' ':
            count += 1
        else:
            break
    return count

def parse_table(f, has_src):
    result = []
    prev_indent = 0
    prev_record = None

    line = f.readline()
    n = 0
    while line:
        indent = get_indent(line)
        fields = line.split()
        if not fields:
            line = f.readline()
            continue
        #print(n, indent, fields[0])
        record = Record.parse(n, has_src, fields)
        if indent > prev_indent:
            prev_record.add_child(record)
            record.parent = prev_record
        else:
            if not prev_record:
                result.append(record)
            else:
                parent = prev_record.parent
                for k in range(prev_indent - indent):
                    parent = parent.parent

                if parent:
                    parent.add_child(record)
                    record.parent = parent
                else:
                    result.append(record)

        prev_record = record
        prev_indent = indent
        line = f.readline()
        n += 1

    return result

def parse_file(f):
    line = f.readline()
    while line:
        fields = line.split()
        if fields == ["COST", "CENTRE", "MODULE", "SRC", "no.", "entries", "%time", "%alloc", "%time", "%alloc"]:
            has_src = True
            break
        if fields == ["COST", "CENTRE", "MODULE", "no.", "entries", "%time", "%alloc", "%time", "%alloc"]:
            has_src = False
            break
        line = f.readline()
    return parse_table(f, has_src)

def print_table(table):
    def print_record(record, indent):
        print((" " * indent) + str(record))
        for child in record.children:
            print_record(child, indent+1)

    for record in table:
        print_record(record, 0)

def percent_color(value):
    zero = QColor.fromHsv(111, 100, 190)
    one = QColor.fromHsv(5, 100, 190)

    if value <= 0:
        return zero
    if value >= 1:
        return one

    return QColor((1 - value) * zero.red() + value * one.red(),
                  (1 - value) * zero.green() + value * one.green(),
                  (1 - value) * zero.blue() + value * one.blue())

class PercentDelegate(QStyledItemDelegate):
    def paint(self, painter, option, index):
        value = index.data()
        if not isinstance(value, float):
            QStyledItemDelegate.paint(self, painter, option, index)
            return

        painter.save()
        if option.state & QStyle.StateFlag.State_Selected:
            painter.fillRect(option.rect, option.palette.highlight())
        else:
            painter.fillRect(option.rect, option.palette.base())

        percent = value
        if percent is None:
            percent = 0
        if percent > 100:
            percent = 100
        w = option.rect.width() * percent / 100
        color = percent_color(percent / 100)
        painter.fillRect(option.rect.x(), option.rect.y(), w, option.rect.height(), color)
        painter.drawText(option.rect, 0, str(value) + " %")
        painter.restore()

#     def sizeHint(self, option, index):
#         pass

class DataModel(QAbstractItemModel):
    def __init__(self, record):
        QAbstractItemModel.__init__(self)
        self.record = record

    def index(self, row, column, parent):
        if not self.hasIndex(row, column, parent):
            return QModelIndex()

        if not parent.isValid():
            parentItem = self.record
        else:
            parentItem = parent.internalPointer()

        if row < len(parentItem.children):
            childItem = parentItem.children[row]
            return self.createIndex(row, column, childItem)
        else:
            return QModelIndex()

    def parent(self, index):
        if not index.isValid():
            return QModelIndex()

        childItem = index.internalPointer()
        parentItem = childItem.parent
        if not parentItem:
            #print("{}: no parent".format(childItem))
            return QModelIndex()
        return self.createIndex(parentItem.row(), 0, parentItem)

    def columnCount(self, parent):
        return len(column_names)

    def rowCount(self, parent):
        if parent.column() > 0:
            return 0

        if not parent.isValid():
            parentItem = self.record
        else:
            parentItem = parent.internalPointer()

        return len(parentItem.children)

#     def sort(self, column, order):
#         key = lambda r : r.data(column)
#         self.record.children.sort(key = key)

    def data(self, index, role):
        if not index.isValid():
            return QVariant()

        item = index.internalPointer()
        #print("data({}, {}) = {}".format(index.row(), index.column(), item))

        if role == QtCore.Qt.ItemDataRole.UserRole:
            return item.data(index.column())
        elif role == QtCore.Qt.ItemDataRole.DisplayRole:
            value = item.data(index.column())
            if isinstance(value, float):
                value = round(value, 2)
            if not isinstance(value, (int, float, str)) and value is not None:
                value = str(value)
            return value
        elif role == QtCore.Qt.ItemDataRole.UserRole + 1:
            #print("in data")
            #print("in data: {}".format(item))
            return item
        else:
            return QVariant()

    def headerData(self, section, orientation, role):
        if role == QtCore.Qt.ItemDataRole.DisplayRole and orientation == QtCore.Qt.Orientation.Horizontal:
            if section < 0 or section >= len(column_names):
                return QVariant()
            return column_names[section]
        else:
            return QVariant()

class FilterModel(QSortFilterProxyModel):
    def __init__(self, parent):
        QSortFilterProxyModel.__init__(self, parent)
        self.tab = parent
        self.individual_time = None
        self.individual_alloc = None
        self.inherited_time = None
        self.inherited_alloc = None
        self.name = None

    def check(self, sourceRow, sourceParent):
        idx = self.sourceModel().index(sourceRow, NAME_COLUMN, sourceParent)
        if not idx.isValid():
            return False
        record = self.sourceModel().data(idx, QtCore.Qt.ItemDataRole.UserRole + 1)

        if self.individual_time is not None and self.individual_time > record.individual_time:
            return False

        if self.individual_alloc is not None and self.individual_alloc > record.individual_alloc:
            return False

        if self.inherited_time is not None and self.inherited_time > record.inherited_time:
            return False

        if self.inherited_alloc is not None and self.inherited_alloc > record.inherited_alloc:
            return False

        def good(name):
            search_type = self.tab.search_type.currentData()
            if search_type == SEARCH_EXACT:
                return self.name == name
            elif search_type == SEARCH_CONTAINS:
                return self.name in name
            else:
                if self.regexp:
                    return self.regexp.match(name) is not None
                else:
                    return True

        if self.name and not good(record.name):
        #if self.name and self.name not in record.name:
            return False

        return True

    def check_name(self, search_type, needle, name):
        if search_type == SEARCH_EXACT:
            return needle == name
        elif search_type == SEARCH_CONTAINS:
            return needle in name
        else:
            return re.compile(needle).match(name) is not None

    def filterAcceptsRow(self, sourceRow, sourceParent):
        if self.check(sourceRow, sourceParent):
            return True

        parent = sourceParent
        while parent and parent.isValid():
            if self.check(parent.row(), parent.parent()):
                return True
            parent = parent.parent()

        if self.hasAcceptedChildren(sourceRow, sourceParent):
            return True

        return False

    def hasAcceptedChildren(self, sourceRow, sourceParent):
        item = self.sourceModel().index(sourceRow, NAME_COLUMN, sourceParent)
        if not item.isValid():
            return False

        childCount = item.model().rowCount(item)
        for row in range(childCount):
            if self.check(row, item):
                return True
            if self.hasAcceptedChildren(row, item):
                return True
        return False

    def setFilter(self, name, individual_time, individual_alloc, inherited_time, inherited_alloc):
        self.name = name
        if name:
            self.regexp = re.compile(name)
        self.inherited_time = inherited_time
        self.inherited_alloc = inherited_alloc
        self.individual_time = individual_time
        self.individual_alloc = individual_alloc
        self.invalidateFilter()

    def reset(self):
        self.name = None
        self.regexp = None
        self.inherited_time = None
        self.inherited_alloc = None
        self.individual_time = None
        self.individual_alloc = None
        self.invalidateFilter()

    def search(self, start, value, search_type):
        result = []
        p = self.parent(start)
        row_from = start.row()
        row_to = self.rowCount(p)

        for i in range(2):
            for r in range(row_from, row_to):
                idx = self.index(r, NAME_COLUMN, p)
                if not idx.isValid():
                    continue
                v = self.data(idx, QtCore.Qt.ItemDataRole.DisplayRole)
                if self.check_name(search_type, value, v):
                    result.append(idx)

                tree_idx = self.index(r, 0, p)
                if self.hasChildren(tree_idx):
                    sub_start = self.index(0, 0, tree_idx)
                    sub = self.search(sub_start, value, search_type)
                    result.extend(sub)

            row_from = 0
            row_to = start.row()

        return result

def make_header_menu(tree):
    def toggle(i):
        def trigger():
            hidden = tree.isColumnHidden(i)
            tree.setColumnHidden(i, not hidden)
        return trigger

    menu = QMenu(tree)
    for i, title in enumerate(column_names):
        action = menu.addAction(title)
        action.setCheckable(True)
        action.setChecked(not tree.isColumnHidden(i))
        action.triggered.connect(toggle(i))

    return menu

SEARCH_CONTAINS = 1
SEARCH_EXACT = 2
SEARCH_REGEXP = 3

class TreeView(QWidget):
    def __init__(self, table, parent):
        QWidget.__init__(self, parent)
        self.window = parent
        self.tree = QTreeView(self)
        indent = self.tree.indentation()
        self.tree.setIndentation(indent / 2)

        self.model = DataModel(table)
        self.sorter = sorter = FilterModel(self)
        sorter.setSourceModel(self.model)
        self.tree.setModel(sorter)
        for col in range(3,9):
            self.tree.setItemDelegateForColumn(col, PercentDelegate(self))
        self.tree.header().setContextMenuPolicy(QtCore.Qt.ContextMenuPolicy.CustomContextMenu)
        self.tree.header().customContextMenuRequested.connect(self._on_header_menu)
        self.tree.setSortingEnabled(True)
        self.tree.setAutoExpandDelay(0)
        self.tree.resizeColumnToContents(0)
        self.tree.resizeColumnToContents(NAME_COLUMN)
        self.tree.expand(self.sorter.index(0,0))
        #self.tree.expandAll()

        self.tree.setContextMenuPolicy(QtCore.Qt.ContextMenuPolicy.CustomContextMenu)
        self.tree.customContextMenuRequested.connect(self._on_tree_menu)

        searchbox = QHBoxLayout()
        self.search = QLineEdit(self)

        searchbox.addWidget(self.search)

        self.search_type = QComboBox(self)
        self.search_type.addItem("Contains", SEARCH_CONTAINS)
        self.search_type.addItem("Exact", SEARCH_EXACT)
        self.search_type.addItem("Reg.Exp", SEARCH_REGEXP)
        searchbox.addWidget(self.search_type)

        btn = QPushButton("&Search", self)
        searchbox.addWidget(btn)
        btn.clicked.connect(self._on_search)

        btn = QPushButton("&Next", self)
        searchbox.addWidget(btn)
        btn.clicked.connect(self._on_search_next)

        filterbox = QHBoxLayout()

        label = QLabel("Time Individual", self)
        filterbox.addWidget(label)
        self.individual_time = QSpinBox(self)
        self.individual_time.setMinimum(0)
        self.individual_time.setMaximum(100)
        self.individual_time.setSuffix(" %")
        filterbox.addWidget(self.individual_time)

        label = QLabel("Alloc Individual", self)
        filterbox.addWidget(label)
        self.individual_alloc = QSpinBox(self)
        self.individual_alloc.setMinimum(0)
        self.individual_alloc.setMaximum(100)
        self.individual_alloc.setSuffix(" %")
        filterbox.addWidget(self.individual_alloc)

        label = QLabel("Time Inherited", self)
        filterbox.addWidget(label)
        self.inherited_time = QSpinBox(self)
        self.inherited_time.setMinimum(0)
        self.inherited_time.setMaximum(100)
        self.inherited_time.setSuffix(" %")
        filterbox.addWidget(self.inherited_time)

        label = QLabel("Alloc Inherited", self)
        filterbox.addWidget(label)
        self.inherited_alloc = QSpinBox(self)
        self.inherited_alloc.setMinimum(0)
        self.inherited_alloc.setMaximum(100)
        self.inherited_alloc.setSuffix(" %")
        filterbox.addWidget(self.inherited_alloc)

        btn = QPushButton("&Filter", self)
        btn.clicked.connect(self._on_filter)
        filterbox.addWidget(btn)
        btn = QPushButton("&Reset", self)
        filterbox.addWidget(btn)
        btn.clicked.connect(self._on_reset_filter)

        vbox = QVBoxLayout()
        vbox.addLayout(searchbox)
        vbox.addLayout(filterbox)
        vbox.addWidget(self.tree)
        self.setLayout(vbox)

        self._search_idxs = None
        self._search_idx_no = 0

    def _expand_to(self, idx):
        idxs = [idx]
        parent = idx
        while parent and parent.isValid():
            parent = self.sorter.parent(parent)
            idxs.append(parent)
        #print(idxs)
        for idx in reversed(idxs[:-1]):
            data = self.sorter.data(idx, QtCore.Qt.ItemDataRole.DisplayRole)
            #print(data)
            self.tree.expand(idx)

    def _on_search(self):
        text = self.search.text()
        selected = self.tree.selectedIndexes()
#         if selected:
#             start = selected[0]
#         else:
        start = self.sorter.index(0,NAME_COLUMN)
        search_type = self.search_type.currentData()
        if search_type == SEARCH_EXACT:
            method = QtCore.Qt.MatchFlag.MatchFixedString
        elif search_type == SEARCH_CONTAINS:
            method = QtCore.Qt.MatchFlag.MatchContains
        else:
            method = QtCore.Qt.MatchRegExp

        self._search_idxs = idxs = self.sorter.search(start, text, search_type)
        if idxs:
            self.window.statusBar().showMessage("Found: {} occurence(s)".format(len(idxs)))
            self._search_idx_no = 0
            idx = idxs[0]
            self._locate(idx)
        else:
            self.window.statusBar().showMessage("Not found")

    def _locate(self, idx):
        self.tree.resizeColumnToContents(0)
        self.tree.resizeColumnToContents(NAME_COLUMN)
        self._expand_to(idx)
        self.tree.setCurrentIndex(idx)
        #self.tree.selectionModel().select(idx, QItemSelectionModel.SelectionFlag.ClearAndSelect | QItemSelectionModel.SelectionFlag.Current | QItemSelectionModel.SelectionFlag.Rows)
        #self.tree.scrollTo(idx, QAbstractItemView.ScrollHint.PositionAtCenter)

    def _on_search_next(self):
        if self._search_idxs:
            n = len(self._search_idxs)
            self._search_idx_no = (self._search_idx_no + 1) % n
            idx = self._search_idxs[self._search_idx_no]
            self.window.statusBar().showMessage("Occurence {} of {}".format(self._search_idx_no, n))
            self._locate(idx)
        else:
            self.window.statusBar().showMessage("No search results")

    def _on_filter(self):
        self.sorter.setFilter(self.search.text(), self.individual_time.value(), self.individual_alloc.value(), self.inherited_time.value(), self.inherited_alloc.value())

    def _on_reset_filter(self):
        self.sorter.reset()

    def _on_header_menu(self, pos):
        menu = make_header_menu(self.tree)
        menu.exec_(self.mapToGlobal(pos))

    def _on_tree_menu(self, pos):
        index = self.tree.indexAt(pos)
        #print("index: {}".format(index))
        if index.isValid():
            record = self.sorter.data(index, QtCore.Qt.ItemDataRole.UserRole + 1)
            #print("okay?..")
            #print("context: {}".format(record))
            menu = self.window.make_item_menu(self.model, record)
            menu.exec_(self.tree.viewport().mapToGlobal(pos))

class Viewer(QMainWindow):
    def __init__(self, table):
        QMainWindow.__init__(self)
        self.tabs = QTabWidget(self)
        main = TreeView(table, self)
        self.tabs.addTab(main, "All")
        self.setCentralWidget(self.tabs)
        self.statusBar().showMessage("Ready.")

    def make_item_menu(self, model, record):
        def reverse_search():
            root = model.record
            reverse = root.reverse_tree(record)

            widget = TreeView(reverse, self)
            self.tabs.addTab(widget, "Calls to {}".format(record.name))

        def forward_search():
            root = model.record
            tree = root.forward_tree(record)

            widget = TreeView(tree, self)
            self.tabs.addTab(widget, "Calls of {}".format(record.name))

        def focus():
            root = Record.new(record.get_max_id(), "Root")
            root.add_child(record)
            widget = TreeView(root, self)
            self.tabs.addTab(widget, "Narrowed view: {}".format(record.name))

        menu = QMenu(self)
        menu.addAction("Narrow view to this item").triggered.connect(focus)
        menu.addAction("Group all outgoing calls").triggered.connect(forward_search)
        menu.addAction("Group all incoming calls").triggered.connect(reverse_search)

        return menu

if __name__ == "__main__":
#     root = Record.new(0, "root", "root", "root")
#     Record.insert(root, [Record.new(1), Record.new(4), Record.new(51, name="5")])
#     Record.insert(root, [Record.new(2), Record.new(4), Record.new(52, name="5")])
#     Record.insert(root, [Record.new(7), Record.new(4), Record.new(60)])
#     Record.insert(root, [Record.new(3), Record.new(4), Record.new(53, name="5")])
#     Record.insert(root, [Record.new(3), Record.new(4), Record.new(54, name="5")])
#     root.flatten()
#     print_table([root])
#
#     new_root = root.forward_tree(Record.new(4))
#     print_table([new_root])

    path = sys.argv[1]
    with open(path) as f:
        table = parse_file(f)

    app = QApplication(sys.argv)
    window = Viewer(table[0])
    window.show()

    sys.exit(app.exec_())

