# -*- coding: utf-8 -*-
#
# Live Search plugin for Zim Desktop Wiki (requires Zim 0.77 or newer)
#
# Searches the whole notebook while you type, using the same search engine as
# "Search > Search..." (AND, OR, NOT, "phrase", Section:, Tag:, ...).
# Every result shows text snippets with the search terms highlighted.
# Clicking a result opens the page and highlights the terms.
#
# Copyright 2026 Heinz Bundschuh, written with the help of Claude (Anthropic)
# License: GPL v2 or later (same as Zim)

import logging
import re

from gi.repository import Gtk, Gdk, GLib, Pango

from zim.actions import action
from zim.gui.mainwindow import MainWindowExtension
from zim.gui.widgets import Dialog, InputEntry, ScrolledWindow
from zim.notebook import Path
from zim.plugins import PluginClass

try:
	# The page search was rewritten in Zim 0.77, older versions do not have these
	from zim.search import PageSearch, SearchCancelledException
	from zim.parse.searchquery import SearchFlag, SEARCH_CASE_SENSITIVE, SEARCH_WHOLE_WORD
	from zim.parse.tokenlist import tokens_to_text
except ImportError:
	PageSearch = None

logger = logging.getLogger('zim.plugins.livesearch')

__version__ = '1.0.0'

# --- translations -------------------------------------------------------------------------
# Strings that also exist in Zim are translated by Zim itself. For the plugin's own strings a
# small built-in table is used. The language is taken from Zim's active translation, so the
# plugin always follows the language of the Zim user interface.

_LANGUAGE_PROBE = {  # language: Zim's translation of 'No results'
	'de': 'Keine Treffer',
}

_TRANSLATIONS = {
	'de': {
		'Live Search': 'Live-Suche',
		'_Live Search...': '_Live-Suche...',
		'Searches the whole notebook while you type and shows text snippets '
		'with the search terms highlighted for every page found.\n'
		'Open it with Ctrl+Shift+E or from the Tools menu.\n\n'
		'Click or arrow keys: show the page and highlight the terms.\n'
		'Double click or Enter: open the page (and close the window, if set).\n'
		'Esc: close the window.\n\n'
		'Supports the same query syntax as the built-in search: several words '
		'(all must match), OR, NOT or -word, "exact phrase", Section:, Tag:, '
		'Name:, Links: etc.\n\n'
		'Requires Zim 0.77 or newer.\n'
		'Version %s':
			'Durchsucht das ganze Notizbuch schon beim Eintippen und zeigt zu jeder '
			'gefundenen Seite Textausschnitte mit den markierten Suchbegriffen.\n'
			'Öffnen mit Strg+Umschalt+E oder über das Menü Werkzeuge.\n\n'
			'Klick oder Pfeiltasten: Seite anzeigen und Begriffe markieren.\n'
			'Doppelklick oder Enter: Seite öffnen (und Fenster schließen, falls eingestellt).\n'
			'Esc: Fenster schließen.\n\n'
			'Es gelten dieselben Suchausdrücke wie bei der eingebauten Suche: mehrere '
			'Wörter (alle müssen vorkommen), OR, NOT bzw. -wort, "genaue Phrase", '
			'Section:, Tag:, Name:, Links: usw.\n\n'
			'Benötigt Zim 0.77 oder neuer.\n'
			'Version %s',
		'Start searching after this number of characters': 'Suche starten ab Anzahl Zeichen',
		'Delay after the last keystroke (ms)': 'Wartezeit nach dem letzten Tastendruck (ms)',
		'Text snippets per page': 'Textausschnitte pro Seite',
		'Characters shown before and after a match': 'Zeichen vor und nach dem Treffer',
		'Maximum number of pages shown': 'Höchstens so viele Seiten anzeigen',
		'Close the window after double click / Enter': 'Fenster nach Doppelklick / Enter schließen',
		'Window opacity (%)': 'Deckkraft des Fensters (%)',
		'Fully opaque while the mouse is over the window':
			'Voll sichtbar, solange die Maus über dem Fenster ist',
		'Zim 0.77 or newer': 'Zim 0.77 oder neuer',
		'Several words: all must match. Also OR, NOT, "phrase",\n'
		'Section: page, Tag: name, Name: page name, Links: page':
			'Mehrere Wörter: alle müssen vorkommen. Außerdem OR, NOT, "Phrase",\n'
			'Section: Seite, Tag: Name, Name: Seitenname, Links: Seite',
		'Search only in "%s" and its sub-pages': 'Nur in „%s“ und den Unterseiten suchen',
		'Type to search ...': 'Suchbegriff eingeben …',
		'... %i more character(s)': '… noch %i Zeichen',
		'Error: %s': 'Fehler: %s',
		'Incomplete search expression': 'Suchausdruck unvollständig',
		'More than %i pages found, showing the first %i. '
		'Refine the search to narrow it down.':
			'Mehr als %i Seiten gefunden, die ersten %i werden angezeigt. '
			'Suche genauer eingrenzen.',
		'1 page found': '1 Seite gefunden',
		'%i pages found': '%i Seiten gefunden',
	},
}

_language = None


def _detect_language():
	global _language
	if _language is None:
		_language = ''
		try:
			probe = _('No results')
			for lang, translated in _LANGUAGE_PROBE.items():
				if probe == translated:
					_language = lang
					break
		except Exception:
			pass
	return _language


def T(message):
	"""Translate a user interface string"""
	try:
		translated = _(message)  # Zim's own translation, if Zim has this string
	except Exception:
		translated = message
	if translated != message:
		return translated
	return _TRANSLATIONS.get(_detect_language(), {}).get(message, message)


HIGHLIGHT = '<span background="#ffe45c" foreground="#000000"><b>%s</b></span>'


class LiveSearchPlugin(PluginClass):

	plugin_info = {
		'name': T('Live Search'),  # T: plugin name
		'description': T(
			'Searches the whole notebook while you type and shows text snippets '
			'with the search terms highlighted for every page found.\n'
			'Open it with Ctrl+Shift+E or from the Tools menu.\n\n'
			'Click or arrow keys: show the page and highlight the terms.\n'
			'Double click or Enter: open the page (and close the window, if set).\n'
			'Esc: close the window.\n\n'
			'Supports the same query syntax as the built-in search: several words '
			'(all must match), OR, NOT or -word, "exact phrase", Section:, Tag:, '
			'Name:, Links: etc.\n\n'
			'Requires Zim 0.77 or newer.\n'
			'Version %s'
		) % __version__,  # T: plugin description
		'author': 'Heinz Bundschuh',
		'help': 'Help:Searching',
	}

	plugin_preferences = (
		# key, type, label, default, (min, max)
		('min_length', 'int', T('Start searching after this number of characters'), 3, (1, 10)),
		('delay', 'int', T('Delay after the last keystroke (ms)'), 300, (0, 3000)),
		('snippets', 'int', T('Text snippets per page'), 3, (0, 10)),
		('context', 'int', T('Characters shown before and after a match'), 45, (10, 200)),
		('max_results', 'int', T('Maximum number of pages shown'), 200, (10, 5000)),
		('close_on_activate', 'bool', T('Close the window after double click / Enter'), True),
		('opacity', 'int', T('Window opacity (%)'), 100, (20, 100)),
		('opaque_on_hover', 'bool', T('Fully opaque while the mouse is over the window'), True),
	)

	@classmethod
	def check_dependencies(klass):
		ok = PageSearch is not None
		return ok, [(T('Zim 0.77 or newer'), ok, True)]


class LiveSearchMainWindowExtension(MainWindowExtension):

	def __init__(self, plugin, window):
		MainWindowExtension.__init__(self, plugin, window)
		self._dialog = None

	@action(T('_Live Search...'), accelerator='<Primary><shift>E', menuhints='tools')  # T: menu item
	def live_search(self):
		if self._dialog is not None and not self._dialog.destroyed:
			self._dialog.set_section_page(self.window.page)
			self._dialog.present()
		else:
			self._dialog = LiveSearchDialog(self.window, self.plugin.preferences)
			self._dialog.show_all()
		self._dialog.query_entry.grab_focus()
		self._dialog.query_entry.select_region(0, -1)

	def teardown(self):
		if self._dialog is not None and not self._dialog.destroyed:
			self._dialog.destroy()


class LiveSearchDialog(Dialog):

	COL_MARKUP = 0
	COL_SCORE = 1
	COL_NAME = 2

	def __init__(self, window, preferences):
		Dialog.__init__(self, window, T('Live Search'),  # T: dialog title
			buttons=Gtk.ButtonsType.CLOSE, help='Help:Searching',
			defaultwindowsize=(560, 520))
		self.mainwindow = window
		self.notebook = window.notebook
		self.navigation = window.navigation
		self.preferences = preferences
		self.section_page = None

		self._timer = None
		self._generation = 0  # increased on every input change, cancels a running search
		self._running = False
		self._restart = False
		self._find_query = None
		self._regex = None
		self._opening = False  # True while we open a page ourselves
		self._updating = False  # True while the result list is cleared or filled

		# --- input row
		hbox = Gtk.HBox(spacing=5)
		self.vbox.pack_start(hbox, False, True, 0)
		label = Gtk.Label.new_with_mnemonic(T('_Search') + ': ')  # T: input label
		hbox.pack_start(label, False, True, 0)
		self.query_entry = InputEntry()
		self.query_entry.set_tooltip_text(T(
			'Several words: all must match. Also OR, NOT, "phrase",\n'
			'Section: page, Tag: name, Name: page name, Links: page'))  # T: tooltip
		label.set_mnemonic_widget(self.query_entry)
		hbox.pack_start(self.query_entry, True, True, 0)
		self.spinner = Gtk.Spinner()
		self.spinner.set_no_show_all(True)
		hbox.pack_start(self.spinner, False, True, 0)

		# --- options
		self.uistate.setdefault('case', False)
		self.uistate.setdefault('word', False)
		self.uistate.setdefault('section', False)
		self.uistate.setdefault('last_query', '')
		# options wrap into a second line when the window is narrow (long translated labels)
		opts = Gtk.FlowBox()
		opts.set_selection_mode(Gtk.SelectionMode.NONE)
		opts.set_column_spacing(10)
		opts.set_max_children_per_line(3)
		opts.set_homogeneous(False)
		self.vbox.pack_start(opts, False, True, 0)
		self.case_check = Gtk.CheckButton.new_with_mnemonic(T('Match c_ase'))  # T: option
		self.word_check = Gtk.CheckButton.new_with_mnemonic(T('Whole _word'))  # T: option
		self.section_check = Gtk.CheckButton.new_with_mnemonic(
			T('_Limit search to the current page and sub-pages'))  # T: option
		self.case_check.set_active(bool(self.uistate['case']))
		self.word_check.set_active(bool(self.uistate['word']))
		self.section_check.set_active(bool(self.uistate['section']))
		self.set_section_page(window.page, search=False)
		for w in (self.case_check, self.word_check, self.section_check):
			opts.add(w)
			w.connect('toggled', self._on_input_changed)

		# --- status line
		self.status_label = Gtk.Label(label='')
		self.status_label.set_xalign(0)
		self.status_label.set_ellipsize(Pango.EllipsizeMode.END)
		self.vbox.pack_start(self.status_label, False, True, 0)

		# --- results
		self.model = Gtk.ListStore(str, int, str)  # COL_MARKUP, COL_SCORE, COL_NAME
		self.model.set_sort_column_id(self.COL_SCORE, Gtk.SortType.DESCENDING)
		self.treeview = Gtk.TreeView(model=self.model)
		self.treeview.set_headers_visible(False)
		self.treeview.set_enable_search(False)  # typing goes to our entry, not to a treeview popup
		self.cell = Gtk.CellRendererText()
		self.cell.set_property('wrap-mode', Pango.WrapMode.WORD_CHAR)
		self.cell.set_property('wrap-width', 500)
		self.cell.set_property('ypad', 4)
		column = Gtk.TreeViewColumn('', self.cell, markup=self.COL_MARKUP)
		self.treeview.append_column(column)
		self.treeview.get_selection().set_mode(Gtk.SelectionMode.BROWSE)
		scrolled = ScrolledWindow(self.treeview)
		self.vbox.pack_start(scrolled, True, True, 0)

		# --- signals
		self.query_entry.connect('changed', self._on_input_changed)
		self.query_entry.connect('activate', self._on_entry_activate)
		self.query_entry.connect('key-press-event', self._on_entry_key)
		self.treeview.get_selection().connect('changed', self._on_selection_changed)
		self.treeview.connect('row-activated', self._on_row_activated)
		self.treeview.connect('button-release-event', self._on_tree_click)
		self.treeview.connect('key-press-event', self._on_tree_key)
		scrolled.connect('size-allocate', self._on_size_allocate)
		self.connect('destroy', self._on_destroy)

		# --- transparency: see-through while reading the page below, opaque under the mouse
		self._mouse_inside = False
		self.add_events(Gdk.EventMask.ENTER_NOTIFY_MASK | Gdk.EventMask.LEAVE_NOTIFY_MASK)
		self.connect('enter-notify-event', self._on_enter_leave, True)
		self.connect('leave-notify-event', self._on_enter_leave, False)
		self._prefs_handler = preferences.connect('changed', self._on_preferences_changed)
		self._update_opacity()

		# restore the last query (selected, so typing replaces it)
		if self.uistate['last_query']:
			self.query_entry.set_text(self.uistate['last_query'])
			self.query_entry.select_region(0, -1)
		else:
			self._set_status(T('Type to search ...'))  # T: status

	# ------------------------------------------------------------------ helpers

	def set_section_page(self, page, search=True):
		'''Set the page used by "Limit to current page and sub-pages"'''
		changed = getattr(page, 'name', None) != getattr(self.section_page, 'name', None)
		self.section_page = page
		self.section_check.set_sensitive(page is not None)
		if page is not None:
			self.section_check.set_tooltip_text(T('Search only in "%s" and its sub-pages') % page.name)  # T: tooltip
		else:
			self.section_check.set_tooltip_text(None)
		if search and changed and self.section_check.get_active():
			self._on_input_changed()

	def _set_status(self, text, busy=False):
		self.status_label.set_text(text)
		if busy:
			self.spinner.show()
			self.spinner.start()
		else:
			self.spinner.stop()
			self.spinner.hide()

	def _get_flags(self):
		flags = SearchFlag(0)
		if self.case_check.get_active():
			flags |= SEARCH_CASE_SENSITIVE
		if self.word_check.get_active():
			flags |= SEARCH_WHOLE_WORD
		return flags

	def _clear_results(self):
		self._updating = True
		try:
			self.model.clear()
		finally:
			self._updating = False
		self._scroll_to_top()

	def _scroll_to_top(self):
		'''Rows are inserted sorted by score, which moves the visible part of the list.
		As long as the user did not select a result, keep the best results in view.'''
		if self._selected_name() is None:
			adj = self.treeview.get_vadjustment()
			if adj is not None:
				adj.set_value(adj.get_lower())

	def _on_size_allocate(self, widget, allocation):
		# allocation of the scrolled window does not depend on the scrollbar, so this is stable
		width = max(200, allocation.width - 30)
		if self.cell.get_property('wrap-width') != width:
			self.cell.set_property('wrap-width', width)

	def save_uistate(self):
		self.uistate['case'] = self.case_check.get_active()
		self.uistate['word'] = self.word_check.get_active()
		self.uistate['section'] = self.section_check.get_active()
		self.uistate['last_query'] = self.query_entry.get_text()

	def _update_opacity(self):
		if self.destroyed:
			return
		opacity = max(20, min(100, self.preferences['opacity'])) / 100.0
		if self._mouse_inside and self.preferences['opaque_on_hover']:
			opacity = 1.0
		if abs(self.get_opacity() - opacity) > 0.001:
			self.set_opacity(opacity)

	def _on_enter_leave(self, widget, event, inside):
		if event.detail == Gdk.NotifyType.INFERIOR:
			return False  # pointer moved between the window and one of its child widgets
		self._mouse_inside = inside
		self._update_opacity()
		return False

	def _on_preferences_changed(self, *a):
		self._update_opacity()

	def _on_destroy(self, *a):
		self._generation += 1  # cancel a running search
		if self._timer:
			GLib.source_remove(self._timer)
			self._timer = None
		try:
			self.preferences.disconnect(self._prefs_handler)
		except Exception:
			pass
		try:
			self.save_uistate()
		except Exception:
			logger.debug('Live Search: could not save ui state', exc_info=True)

	# ------------------------------------------------------------------ search

	def _on_input_changed(self, *a):
		if self._timer:
			GLib.source_remove(self._timer)
			self._timer = None
		self._generation += 1  # a running search sees this and stops

		text = self.query_entry.get_text().strip()
		min_length = self.preferences['min_length']
		if not text or len(text) < min_length:
			self._clear_results()
			self._find_query = self._regex = None
			if not text:
				self._set_status(T('Type to search ...'))  # T: status
			else:
				self._set_status(T('... %i more character(s)') % (min_length - len(text)))  # T: status
			return

		self._set_status(T('Searching ...'), busy=True)  # T: status
		self._timer = GLib.timeout_add(max(0, self.preferences['delay']), self._start_search)

	def _start_search(self):
		self._timer = None
		if self._running:
			# called while a search is running (from inside its ui callback): restart afterwards
			self._restart = True
			return False
		self._running = True
		try:
			while True:
				self._restart = False
				generation = self._generation
				try:
					self._run_search(generation)
				except SearchCancelledException:
					pass
				except Exception as error:
					logger.exception('Live Search: error while searching')
					if not self.destroyed:
						self._set_status(T('Error: %s') % error)  # T: status
				if not self._restart or self.destroyed:
					break
		finally:
			self._running = False
		return False

	def _ui_callback(self, generation):
		def callback():
			while Gtk.events_pending():
				Gtk.main_iteration_do(False)
			if self.destroyed or generation != self._generation:
				raise SearchCancelledException
		return callback

	def _run_search(self, generation):
		string = self.query_entry.get_text().strip()
		if self.section_check.get_active() and self.section_page is not None:
			string = 'Section: "%s" and (%s)' % (self.section_page.name, string)

		callback = self._ui_callback(generation)
		page_search = PageSearch(self.notebook, callback)
		try:
			query = page_search.parse_page_search_query(string, self._get_flags())
		except Exception as error:
			# e.g. while typing an incomplete expression
			self._clear_results()
			self._set_status(T('Incomplete search expression'))  # T: status
			logger.debug('Live Search: query not parsed: %r (%s)', string, error)
			return

		find_query = page_search.find_query_from_search_query(query)
		self._find_query = find_query if find_query else None
		self._regex = getattr(find_query, 'regex', None) if find_query else None

		self._clear_results()
		max_results = self.preferences['max_results']
		count = 0
		limited = False
		for result in page_search.search_pages(query):
			if generation != self._generation:
				raise SearchCancelledException
			if count >= max_results:
				limited = True
				break
			name = result.path.name
			snippets = self._make_snippets(result.path)
			self._updating = True
			try:
				self.model.append((self._row_markup(name, result.search_score, snippets),
								   result.search_score, name))
			finally:
				self._updating = False
			count += 1
			if count == 1 or count % 10 == 0:
				self._scroll_to_top()
				callback()  # show first results immediately, keep typing responsive

		self._scroll_to_top()
		if count == 0:
			self._set_status(T('No results'))  # T: status
		elif limited:
			self._set_status(T('More than %i pages found, showing the first %i. '
								'Refine the search to narrow it down.') % (max_results, max_results))  # T: status
		elif count == 1:
			self._set_status(T('1 page found'))  # T: status
		else:
			self._set_status(T('%i pages found') % count)  # T: status

	# ------------------------------------------------------------------ snippets

	def _page_text(self, path):
		page = self.notebook.get_page(path)
		tree = page.get_parsetree()
		if not tree:
			return ''
		text = tokens_to_text(tree.iter_tokens())
		# the page title is already shown in the result row, drop it from the snippet text
		first, sep, rest = text.lstrip().partition('\n')
		if sep and first.strip().lower() == path.basename.replace('_', ' ').lower():
			text = rest
		return text

	def _make_snippets(self, path):
		max_snippets = self.preferences['snippets']
		regex = self._regex
		if not regex or max_snippets <= 0:
			return []
		try:
			text = self._page_text(path)
		except Exception:
			logger.debug('Live Search: could not read %s', path, exc_info=True)
			return []
		context = self.preferences['context']
		snippets = []
		last_end = -1
		for m in regex.finditer(text):
			if m.end() == m.start():
				continue
			if m.start() < last_end:  # already inside the previous snippet
				continue
			start = max(0, m.start() - context)
			end = min(len(text), m.end() + context)
			# do not cut words at the borders
			while start > 0 and not text[start - 1].isspace() and m.start() - start < context + 15:
				start -= 1
			while end < len(text) and not text[end].isspace() and end - m.end() < context + 15:
				end += 1
			snippets.append(self._highlight(text, start, end, regex))
			last_end = end
			if len(snippets) >= max_snippets:
				break
		return snippets

	@staticmethod
	def _clean(s):
		return GLib.markup_escape_text(re.sub(r'\s+', ' ', s))

	def _highlight(self, text, start, end, regex):
		window = text[start:end]
		parts = []
		pos = 0
		for m in regex.finditer(window):
			if m.end() == m.start():
				continue
			parts.append(self._clean(window[pos:m.start()]))
			parts.append(HIGHLIGHT % self._clean(m.group(0)))
			pos = m.end()
		parts.append(self._clean(window[pos:]))
		snippet = ''.join(parts).strip()
		if start > 0:
			snippet = '… ' + snippet
		if end < len(text):
			snippet = snippet + ' …'
		return snippet

	def _row_markup(self, name, score, snippets):
		escaped = [GLib.markup_escape_text(p) for p in name.split(':')]
		escaped[-1] = '<b>%s</b>' % escaped[-1]
		title = '<span size="large">%s</span>  <span foreground="#888888">(%i)</span>' % (
			':'.join(escaped), score)
		if snippets:
			return title + '\n' + '\n'.join('<small>%s</small>' % s for s in snippets)
		return title

	# ------------------------------------------------------------------ open pages

	def _selected_name(self):
		model, treeiter = self.treeview.get_selection().get_selected()
		if treeiter is None:
			return None
		return model[treeiter][self.COL_NAME]

	def _open(self, name, close=False):
		if not name:
			return
		self._opening = True
		try:
			pageview = self.navigation.open_page(Path(name))
			if pageview is None:
				pageview = self.mainwindow.pageview
			if self._find_query:
				pageview.show_find(self._find_query, highlight=True)
		except Exception:
			logger.exception('Live Search: could not open page: %s', name)
		finally:
			self._opening = False

		if close and self.preferences['close_on_activate']:
			self.destroy()
		else:
			# show_find() moved the keyboard focus to the main window - take it back
			def refocus():
				if not self.destroyed:
					self.present()
					self.treeview.grab_focus()
				return False
			GLib.idle_add(refocus)

	def _on_selection_changed(self, selection):
		if self._opening or self._updating:
			return  # caused by clearing / filling the list, not by the user
		name = self._selected_name()
		if name:
			self._open(name)

	def _on_tree_click(self, treeview, event):
		# a click on the row that is already selected does not change the selection, open it anyway
		if event.button != 1 or event.type != Gdk.EventType.BUTTON_RELEASE:
			return False
		hit = treeview.get_path_at_pos(int(event.x), int(event.y))
		if hit:
			name = self.model[hit[0]][self.COL_NAME]
			if name == self._selected_name() and name != getattr(self.mainwindow.page, 'name', None):
				self._open(name)
		return False

	def _on_row_activated(self, treeview, path, column):
		self._open(self.model[path][self.COL_NAME], close=True)

	def _on_entry_activate(self, entry):
		if self._timer:  # Enter pressed before the delay passed: search now
			GLib.source_remove(self._timer)
			self._start_search()
		if self.destroyed:
			return
		name = self._selected_name()
		if name is None and len(self.model):
			name = self.model[0][self.COL_NAME]
		self._open(name, close=True)

	def _on_entry_key(self, entry, event):
		key = Gdk.keyval_name(event.keyval)
		if key in ('Down', 'Page_Down', 'KP_Down') and len(self.model):
			self.treeview.grab_focus()
			self.treeview.set_cursor(Gtk.TreePath(0), None, False)
			return True
		return False

	def _on_tree_key(self, treeview, event):
		key = Gdk.keyval_name(event.keyval)
		if key in ('Up', 'KP_Up'):
			path, column = treeview.get_cursor()
			if path is None or path.get_indices() == [0]:
				self.query_entry.grab_focus()  # back to the search field from the first row
				return True
		return False
