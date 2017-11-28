import collections

import pycam.Gui.Settings
import pycam.Utils.log


log = pycam.Utils.log.get_logger()


UISection = collections.namedtuple("UISection", ("add_func", "clear_func", "widgets"))
UIWidget = collections.namedtuple("UIWidget", ("name", "obj", "weight", "args"))
UIHandler = collections.namedtuple("UIHandler", ("func", "args"))
UIEvent = collections.namedtuple("UIEvent", ("handlers", "blocker_tokens"))
UIChain = collections.namedtuple("UIChain", ("func", "weight"))


__event_handlers = []
__mainloop = []


def get_mainloop(use_gtk=False):
    """create new or return an existing mainloop

    @param use_gtk: supply Gtk with timeslots for event handling (active if this parameter is True
        at least once)
    """
    try:
        mainloop = __mainloop[0]
    except IndexError:
        mainloop = AsyncIOMainLoop()
        __mainloop.append(mainloop)
    if use_gtk:
        mainloop.enable_gtk()
    return mainloop


class AsyncIOMainLoop:

    PERIOD_SECONDS = 0.05

    def __init__(self):
        import asyncio
        self._asyncio = asyncio
        self.loop = self._asyncio.get_event_loop()
        self._stopped = False
        self._use_gtk = False

    def enable_gtk(self):
        if not self._use_gtk:
            from gi.repository import GLib
            from gi.repository import Gtk
            self._gtk_context = GLib.MainContext.default()
            self._gtk = Gtk
            self._use_gtk = True

            async def start_gtk():
                await self._asyncio.sleep(0)
                self._gtk.main()

            self._asyncio.async(start_gtk())

            def regular_gtk_update():
                self.update()
                if not self._stopped:
                    self.loop.call_later(self.PERIOD_SECONDS, regular_gtk_update)

            self.loop.call_later(self.PERIOD_SECONDS, regular_gtk_update)

    def run(self):
        if not self._stopped:
            try:
                self.loop.run_forever()
            except KeyboardInterrupt:
                pass
            finally:
                self.loop.close()

    def stop(self):
        self._stopped = True
        if self._use_gtk:
            self._gtk.main_quit()
        self.loop.stop()

    def update(self):
        if self._use_gtk:
            while self._gtk_context.pending():
                self._gtk_context.iteration(False)


def get_event_handler():
    if not __event_handlers:
        __event_handlers.append(EventCore())
    return __event_handlers[0]


class EventCore(pycam.Gui.Settings.Settings):

    def __init__(self):
        super(EventCore, self).__init__()
        self.event_handlers = {}
        self.ui_sections = {}
        self.chains = {}
        self.state_dumps = []
        self.namespace = {}

    def register_event(self, event, func, *args):
        if event not in self.event_handlers:
            self.event_handlers[event] = UIEvent([], [])
        self.event_handlers[event].handlers.append(UIHandler(func, args))

    def unregister_event(self, event, func):
        if event in self.event_handlers:
            removal_list = []
            handlers = self.event_handlers[event]
            for index, item in enumerate(handlers.handlers):
                if func == item.func:
                    removal_list.append(index)
            removal_list.reverse()
            for index in removal_list:
                handlers.handlers.pop(index)
        else:
            log.info("Trying to unregister an unknown event: %s", event)

    def emit_event(self, event, *args, **kwargs):
        log.debug2("Event emitted: %s", str(event))
        if event in self.event_handlers:
            if self.event_handlers[event].blocker_tokens:
                log.debug2("Ignoring blocked event: %s", str(event))
                return
            # prevent infinite recursion
            self.block_event(event)
            for handler in self.event_handlers[event].handlers:
                handler.func(*(handler.args + args), **kwargs)
            self.unblock_event(event)
        else:
            log.debug("No events registered for event '%s'", str(event))

    def block_event(self, event):
        if event in self.event_handlers:
            self.event_handlers[event].blocker_tokens.append(True)
        else:
            log.info("Trying to block an unknown event: %s", str(event))

    def unblock_event(self, event):
        if event in self.event_handlers:
            if self.event_handlers[event].blocker_tokens:
                self.event_handlers[event].blocker_tokens.pop()
            else:
                log.debug("Trying to unblock non-blocked event '%s'", str(event))
        else:
            log.info("Trying to unblock an unknown event: %s", str(event))

    def register_ui_section(self, section, add_action, clear_action):
        if section not in self.ui_sections:
            self.ui_sections[section] = UISection(None, None, [])
        else:
            log.error("Trying to register a ui section twice: %s", section)
        self.ui_sections[section] = UISection(add_action, clear_action,
                                              self.ui_sections[section].widgets)
        self._rebuild_ui_section(section)

    def unregister_ui_section(self, section):
        if section in self.ui_sections:
            ui_section = self.ui_sections[section]
            while ui_section.widgets:
                ui_section.widgets.pop()
            del self.ui_sections[section]
        else:
            log.info("Trying to unregister a non-existent ui section: %s", str(section))

    def _rebuild_ui_section(self, section):
        if section in self.ui_sections:
            ui_section = self.ui_sections[section]
            if ui_section.add_func or ui_section.clear_func:
                ui_section.widgets.sort(key=lambda x: x.weight)
                ui_section.clear_func()
                for item in ui_section.widgets:
                    ui_section.add_func(item.obj, item.name, **(item.args or {}))
        else:
            log.info("Failed to rebuild unknown ui section: %s", str(section))

    def register_ui(self, section, name, widget, weight=0, args_dict=None):
        if section not in self.ui_sections:
            log.info("Tried to register widget for non-existing UI: %s -> %s", name, section)
            self.ui_sections[section] = UISection(None, None, [])
        current_widgets = [item.obj for item in self.ui_sections[section].widgets]
        if (widget is not None) and (widget in current_widgets):
            log.info("Tried to register widget twice: %s -> %s", section, name)
            return
        self.ui_sections[section].widgets.append(UIWidget(name, widget, weight, args_dict))
        self._rebuild_ui_section(section)

    def unregister_ui(self, section, widget):
        if (section in self.ui_sections) or (None in self.ui_sections):
            if section not in self.ui_sections:
                section = None
            ui_section = self.ui_sections[section]
            removal_list = []
            for index, item in enumerate(ui_section.widgets):
                if item.obj == widget:
                    removal_list.append(index)
            removal_list.reverse()
            for index in removal_list:
                ui_section.widgets.pop(index)
            self._rebuild_ui_section(section)
        else:
            log.info("Trying to unregister unknown ui section: %s", section)

    def register_chain(self, name, func, weight=100):
        if name not in self.chains:
            self.chains[name] = []
        self.chains[name].append(UIChain(func, weight))
        self.chains[name].sort(key=lambda item: item.weight)

    def unregister_chain(self, name, func):
        if name in self.chains:
            for index, data in enumerate(self.chains[name]):
                if data.func == func:
                    self.chains[name].pop(index)
                    break
            else:
                log.info("Trying to unregister unknown function from %s: %s", name, func)
        else:
            log.info("Trying to unregister from unknown chain: %s", name)

    def call_chain(self, name, *args, **kwargs):
        if name in self.chains:
            for data in self.chains[name]:
                data.func(*args, **kwargs)
        else:
            # this may happen during startup
            log.debug("Called an unknown chain: %s", name)

    def reset_state(self):
        pass

    def register_namespace(self, name, value):
        if name in self.namespace:
            log.info("Trying to register the same key in namespace twice: %s", str(name))
        self.namespace[name] = value

    def unregister_namespace(self, name):
        if name not in self.namespace:
            log.info("Tried to unregister an unknown name from namespace: %s", str(name))

    def get_namespace(self):
        return self.namespace
