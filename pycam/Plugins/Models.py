# -*- coding: utf-8 -*-
"""
Copyright 2011 Lars Kruse <devel@sumpfralle.de>

This file is part of PyCAM.

PyCAM is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

PyCAM is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU General Public License for more details.

You should have received a copy of the GNU General Public License
along with PyCAM.  If not, see <http://www.gnu.org/licenses/>.
"""

import pycam.Plugins
from pycam.Utils import get_non_conflicting_name


_GTK_COLOR_MAX = 65535.0


class Models(pycam.Plugins.ListPluginBase):

    UI_FILE = "models.ui"
    CATEGORIES = ["Model"]
    ICONS = {"visible": "visible.svg", "hidden": "visible_off.svg"}
    FALLBACK_COLOR = {"red": 0.5, "green": 0.5, "blue": 1.0, "alpha": 1.0}
    COLLECTION_ITEM_TYPE = pycam.Flow.data_models.Model

    def setup(self):
        if self.gui:
            self.model_frame = self.gui.get_object("ModelBox")
            self.model_frame.unparent()
            self.core.register_ui("main", "Models", self.model_frame, weight=-50)
            model_handling_obj = self.gui.get_object("ModelHandlingNotebook")

            def clear_model_handling_obj():
                for index in range(model_handling_obj.get_n_pages()):
                    model_handling_obj.remove_page(0)

            def add_model_handling_item(item, name):
                model_handling_obj.append_page(item, self._gtk.Label(name))

            self.core.register_ui_section("model_handling", add_model_handling_item,
                                          clear_model_handling_obj)
            self._modelview = self.gui.get_object("ModelView")
            self.set_gtk_modelview(self._modelview)
            self.register_model_update(lambda: self.core.emit_event("model-list-changed"))
            for action, obj_name in ((self.ACTION_UP, "ModelMoveUp"),
                                     (self.ACTION_DOWN, "ModelMoveDown"),
                                     (self.ACTION_DELETE, "ModelDelete"),
                                     (self.ACTION_CLEAR, "ModelDeleteAll")):
                self.register_list_action_button(action, self.gui.get_object(obj_name))
            self._gtk_handlers = []
            self._gtk_handlers.extend((
                (self.gui.get_object("ModelColorButton"), "color-set",
                 self._store_colors_of_selected_models),
                (self._modelview, "row-activated", self._toggle_visibility),
                (self.gui.get_object("NameCell"), "edited", self._edit_model_name)))
            self._treemodel = self.gui.get_object("ModelList")
            self._treemodel.clear()
            selection = self._modelview.get_selection()
            selection.set_mode(self._gtk.SelectionMode.MULTIPLE)
            self._gtk_handlers.append((selection, "changed", "model-selection-changed"))
            self._event_handlers = (
                ("model-selection-changed", self._apply_colors_of_selected_models),
                ("model-list-changed", self._trigger_table_update))
            self.register_gtk_handlers(self._gtk_handlers)
            self.register_event_handlers(self._event_handlers)
            self._apply_colors_of_selected_models()
            # update the model list
            self.core.emit_event("model-list-changed")
        self.core.set("models", self)
        return True

    def teardown(self):
        self.clear_state_items()
        if self.gui and self._gtk:
            self.core.unregister_ui_section("model_handling")
            self.core.unregister_ui("main", self.gui.get_object("ModelBox"))
            self.core.unregister_ui("main", self.model_frame)
            self.unregister_gtk_handlers(self._gtk_handlers)
            self.unregister_event_handlers(self._event_handlers)
        self.core.set("models", None)
        self.clear()
        return True

    def _get_model_gdk_color(self, color_dict):
        return self._gdk.Color(red=int(color_dict["red"] * _GTK_COLOR_MAX),
                               green=int(color_dict["green"] * _GTK_COLOR_MAX),
                               blue=int(color_dict["blue"] * _GTK_COLOR_MAX))

    def _apply_model_color_to_button(self, model, color_button):
        color = model.get_application_value("color")
        if color is not None:
            color_button.set_color(self._get_model_gdk_color(color))
            color_button.set_alpha(int(color["alpha"] * _GTK_COLOR_MAX))

    def _apply_colors_of_selected_models(self, widget=None):
        color_button = self.gui.get_object("ModelColorButton")
        models = self.get_selected()
        color_button.set_sensitive(len(models) > 0)
        if models:
            # use the color of the first model, if it exists
            self._apply_model_color_to_button(models[0], color_button)

    def _store_colors_of_selected_models(self, widget=None):
        color_button = self.gui.get_object("ModelColorButton")
        color = self.gui.get_object("ModelColorButton").get_color()
        for model in self.get_selected():
            model.set_application_value("color", {
                "red": color.red / _GTK_COLOR_MAX,
                "green": color.green / _GTK_COLOR_MAX,
                "blue": color.blue / _GTK_COLOR_MAX,
                "alpha": color_button.get_alpha() / _GTK_COLOR_MAX})
        self.core.emit_event("visual-item-updated")

    def _trigger_table_update(self):
        self.gui.get_object("NameColumn").set_cell_data_func(
            self.gui.get_object("NameCell"), self._visualize_model_name)
        self.gui.get_object("VisibleColumn").set_cell_data_func(
            self.gui.get_object("VisibleSymbol"), self._visualize_visible_state)

    def _edit_model_name(self, cell, path, new_text):
        model = self.get_by_path(path)
        if model and (new_text != model.get_application_value("name")) and new_text:
            model.set_application_value("name", new_text)
            self.core.emit_event("model-list-changed")

    def _visualize_model_name(self, column, cell, model, m_iter, data):
        model_obj = self.get_by_path(model.get_path(m_iter))
        cell.set_property("text", model_obj.get_application_value("name", "No Name"))

    def _visualize_visible_state(self, column, cell, model, m_iter, data):
        model_obj = self.get_by_path(model.get_path(m_iter))
        if model_obj.get_application_value("visible", True):
            cell.set_property("pixbuf", self.ICONS["visible"])
        else:
            cell.set_property("pixbuf", self.ICONS["hidden"])
        color = model_obj.get_application_value("color")
        if color is not None:
            cell.set_property("cell-background-gdk", self._get_model_gdk_color(color))

    def _toggle_visibility(self, treeview, path, clicked_column):
        model_obj = self.get_by_path(path)
        model_obj.set_application_value("visible", not model_obj.get_application_value("visible"))
        self.core.emit_event("visual-item-updated")

    def get_visible(self):
        return [model for model in self.get_all() if model.get_application_value("visible", True)]

    def add_model(self, model, name=None, name_template="Model #%d", color=None):
        if not name:
            name = get_non_conflicting_name(name_template, [m.get_application_value("name")
                                                            for m in self.get_all()])
        self.log.info("Adding new model: %s", name)
        if not color:
            color = self.core.get("color_model")
        if not color:
            color = self.FALLBACK_COLOR.copy()
        new_model = pycam.Flow.data_models.Model(None,
                                                 {"source": {"type": "object", "data": model}})
        new_model.set_application_value("name", name)
        new_model.set_application_value("color", color)
        new_model.set_application_value("visible", True)
