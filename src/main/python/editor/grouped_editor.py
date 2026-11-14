# SPDX-License-Identifier: GPL-2.0-or-later
"""One top-level tab that holds several editors as tabs of its own (Advanced
Keys, QuickBuild). Each editor's rebuild() is still driven by the main window;
this only decides which of them are on show and tells the visible one when it
comes into and goes out of view."""

from editor.basic_editor import BasicEditor
from widgets.editor_container import EditorContainer
from widgets.side_tabs import SideTabs
from util import tr


class GroupedEditor(BasicEditor):

    def __init__(self, context="GroupedEditor"):
        super().__init__()
        self.context = context      # translation context for the tab names
        self.entries = []           # (page, label, editor or None), in order
        self.active_editor = None
        self.is_active = False

        self.tabs = SideTabs()      # the editors down the left, the chosen one beside them
        self.tabs.currentChanged.connect(self.on_tab_changed)
        self.addWidget(self.tabs)

    def add_editor(self, editor, label):
        """A BasicEditor as a tab; shown while its own valid() says so."""
        page = EditorContainer(editor)
        self.entries.append((page, label, editor))
        self.tabs.addTab(page, tr(self.context, label))
        return page

    def add_page(self, widget, label):
        """A plain page that is not an editor of its own."""
        if widget is not None:
            self.entries.append((widget, label, None))
            self.tabs.addTab(widget, tr(self.context, label))
        return widget

    def open_tab(self, label):
        wanted = tr(self.context, label)
        for index in range(self.tabs.count()):
            if self.tabs.tabText(index) == wanted:
                self.tabs.setCurrentIndex(index)
                return True
        return False

    def valid(self):
        return any(editor is None or editor.valid() for _, _, editor in self.entries)

    def rebuild(self, device):
        """Call after the editors inside have been rebuilt: the tabs follow
        which of them are valid for this keyboard."""
        super().rebuild(device)
        wanted = [(page, label) for page, label, editor in self.entries if editor is None or editor.valid()]
        shown = [self.tabs.widget(i) for i in range(self.tabs.count())]
        if shown != [page for page, _ in wanted]:
            current = self.tabs.currentWidget()
            self.tabs.blockSignals(True)
            self.tabs.clear()
            for page, label in wanted:
                self.tabs.addTab(page, tr(self.context, label))
            if current is not None and self.tabs.indexOf(current) >= 0:
                self.tabs.setCurrentWidget(current)
            self.tabs.blockSignals(False)
            self.on_tab_changed(self.tabs.currentIndex())

    def editor_of(self, page):
        for entry_page, _, editor in self.entries:
            if entry_page is page:
                return editor
        return None

    def _set_active_editor(self, editor):
        if editor is self.active_editor:
            return
        if self.active_editor is not None:
            self.active_editor.deactivate()
        self.active_editor = editor
        if editor is not None:
            editor.activate()

    def on_tab_changed(self, index):
        if self.is_active:
            self._set_active_editor(self.editor_of(self.tabs.widget(index)))
            self.page_shown(self.tabs.widget(index))

    def page_shown(self, page):
        """For subclasses: `page` has just come into view."""

    def activate(self):
        self.is_active = True
        self.on_tab_changed(self.tabs.currentIndex())

    def deactivate(self):
        self.is_active = False
        self._set_active_editor(None)
