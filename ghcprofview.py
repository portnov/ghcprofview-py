#!/usr/bin/env python3

import sys

from PyQt5.QtGui import QPainter, QPixmap, QIcon, QStandardItemModel, QStandardItem, QColor
from PyQt5 import QtCore
from PyQt5.QtCore import QRect, QSize, Qt, QObject, QTimer, pyqtSignal, QSettings, QModelIndex, QVariant, QAbstractItemModel, QSortFilterProxyModel, QItemSelectionModel
from PyQt5.QtWidgets import QApplication, QWidget, QToolBar, QMainWindow, QDialog, QVBoxLayout, QHBoxLayout, QAction, QActionGroup, QLabel, QFileDialog, QFrame, QDockWidget, QMessageBox, QListWidget, QListWidgetItem, QMenu, QTreeView, QLineEdit, QPushButton, QAbstractItemView, QStyle, QStyledItemDelegate

column_names = ["Name", "Entries",
                "Time Individual %", "Alloc Individual %",
                "Time Inherited %", "Alloc Inherited %",
                "Time Relative %", "Alloc Relative %",
                "No", "Module", "Source"]

class Record(object):
    def __init__(self, fields):
        self.name = fields[0]
        self.module = fields[1]
        self.src = fields[2]
        k = 0
        if self.src == "<no":
            self.src = "<no>"
            k = 2
        self.no = int(fields[3+k])
        self.entries = int(fields[4+k])
        self.individual_time = float(fields[5+k])
        self.individual_alloc = float(fields[6+k])
        self.inherited_time = float(fields[7+k])
        self.inherited_alloc = float(fields[8+k])
        self.children = []
        self.parent = None

        self._relative_time = None
        self._relative_alloc = None

    def row(self):
        if not self.parent:
            return 0

        return self.parent.children.index(self)

    @property
    def relative_time(self):
        if self._relative_time is None:
            if self.parent is None or self.parent.inherited_time == 0:
                self._relative_time = 100
            else:
                self._relative_time = round(100 * self.inherited_time / self.parent.inherited_time, 2)
        return self._relative_time

    @property
    def relative_alloc(self):
        if self._relative_alloc is None:
            if self.parent is None or self.parent.inherited_alloc == 0:
                self._relative_alloc = 100
            else:
                self._relative_alloc = round(100 * self.inherited_alloc / self.parent.inherited_alloc, 2)
        return self._relative_alloc

    def data(self, col):
        row = [self.name,
                self.entries,
                self.individual_time,
                self.individual_alloc,
                self.inherited_time,
                self.inherited_alloc,
                self.relative_time,
                self.relative_alloc,
                self.no,
                self.module,
                self.src
            ]
        return row[col]

    def __eq__(self, other):
        return self.name == other.name and \
                self.module == other.module and \
                self.src == other.src and \
                self.no == other.no and \
                self.entries == other.entries

    def __repr__(self):
        return "{}: {} ({})".format(self.name, self.inherited_time, len(self.children))

def get_indent(s):
    count = 0
    for c in s:
        if c == ' ':
            count += 1
        else:
            break
    return count

def parse_table(f):
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
        record = Record(fields)
        if indent > prev_indent:
            prev_record.children.append(record)
            record.parent = prev_record
        else:
            if not prev_record:
                result.append(record)
            else:
                parent = prev_record.parent
                for k in range(prev_indent - indent):
                    parent = parent.parent

                if parent:
                    parent.children.append(record)
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
            break
        line = f.readline()
    return parse_table(f)

def print_table(table):
    def print_record(record, indent):
        print((" " * indent) + str(record))
        for child in record.children:
            print_record(child, indent+1)

    for record in table:
        print_record(record, 0)

def percent_color(value):
    zero = QColor(128, 255, 128)
    one = QColor(255, 128, 128)

    return QColor((1 - value) * zero.red() + value * one.red(),
                  (1 - value) * zero.green() + value * one.green(),
                  (1 - value) * zero.blue() + value * one.blue())

class PercentDelegate(QStyledItemDelegate):
    def paint(self, painter, option, index):
        QStyledItemDelegate.paint(self, painter, option, index)
        painter.save()
        if option.state & QStyle.State_Selected:
            painter.fillRect(option.rect, option.palette.highlight())
        else:
            painter.fillRect(option.rect, option.palette.base())

        value = index.data()
        w = option.rect.width() * value / 100
        color = percent_color(value / 100)
        painter.fillRect(option.rect.x(), option.rect.y(), w, option.rect.height(), color)
        painter.drawText(option.rect, 0, str(value))
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

        if role == QtCore.Qt.UserRole:
            return item.data(index.column())
        elif role == QtCore.Qt.DisplayRole:
            return item.data(index.column())
        else:
            return QVariant()

    def headerData(self, section, orientation, role):
        if role == QtCore.Qt.DisplayRole and orientation == QtCore.Qt.Horizontal:
            if section < 0 or section >= len(column_names):
                return QVariant()
            return column_names[section]
        else:
            return QVariant()

class Viewer(QMainWindow):
    def __init__(self, table):
        QMainWindow.__init__(self)
        self.tree = QTreeView(self)
        self.model = DataModel(table)
        self.sorter = sorter = QSortFilterProxyModel(self)
        sorter.setSourceModel(self.model)
        self.tree.setModel(sorter)
        for col in range(2,8):
            self.tree.setItemDelegateForColumn(col, PercentDelegate(self))
        self.tree.setSortingEnabled(True)
        self.tree.setAutoExpandDelay(0)
        self.tree.resizeColumnToContents(0)
        self.tree.expand(self.sorter.index(0,0))
        #self.tree.expandAll()

        hbox = QHBoxLayout()
        self.search = QLineEdit(self)
        btn = QPushButton("Search", self)
        hbox.addWidget(self.search)
        hbox.addWidget(btn)
        btn.clicked.connect(self._on_search)

        vbox = QVBoxLayout()
        vbox.addLayout(hbox)
        vbox.addWidget(self.tree)
        widget = QWidget(self)
        widget.setLayout(vbox)
        self.setCentralWidget(widget)

    def _expand_to(self, idx):
        idxs = [idx]
        parent = idx
        while parent and parent.isValid():
            parent = self.sorter.parent(parent)
            idxs.append(parent)
        #print(idxs)
        for idx in reversed(idxs[:-1]):
            data = self.sorter.data(idx, QtCore.Qt.DisplayRole)
            print(data)
            self.tree.expand(idx)

    def _on_search(self):
        text = self.search.text()
        selected = self.tree.selectedIndexes()
        if selected:
            start = selected[0]
        else:
            start = self.sorter.index(0,0)
        idxs = self.sorter.match(start, QtCore.Qt.DisplayRole, text, 1, QtCore.Qt.MatchRecursive | QtCore.Qt.MatchContains | QtCore.Qt.MatchWrap)
        if idxs:
            self.tree.resizeColumnToContents(0)
            self._expand_to(idxs[0])
            self.tree.selectionModel().select(idxs[0], QItemSelectionModel.ClearAndSelect | QItemSelectionModel.Current | QItemSelectionModel.Rows)
            self.tree.scrollTo(idxs[0], QAbstractItemView.PositionAtCenter)

if __name__ == "__main__":
    path = sys.argv[1]
    with open(path) as f:
        table = parse_file(f)

    app = QApplication(sys.argv)
    window = Viewer(table[0])
    window.show()

    sys.exit(app.exec_())

