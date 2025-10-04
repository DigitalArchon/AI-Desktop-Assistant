#!/usr/bin/env python3
"""
LLM Assistant - System tray app for LLM-powered text and image operations
Requires: python3-gi, python3-pil, python3-requests, python3-xlib
"""

import gi
gi.require_version('Gtk', '3.0')
gi.require_version('AppIndicator3', '0.1')
gi.require_version('Gdk', '3.0')

from gi.repository import Gtk, Gdk, GLib, GdkPixbuf, AppIndicator3, Pango
import requests
import json
import threading
import base64
from io import BytesIO
from PIL import Image, ImageGrab
import os
import subprocess
import time
import re
from Xlib import X, XK, display
from Xlib.ext import record
from Xlib.protocol import rq

class Config:
    """Configuration storage"""
    def __init__(self):
        self.config_dir = os.path.expanduser("~/.config/llm-assistant")
        self.config_file = os.path.join(self.config_dir, "config.json")
        self.load()

    def load(self):
        """Load configuration from file"""
        defaults = {
            "api_url": "https://nano-gpt.com/api/v1/chat/completions",  # NanoGPT default
            "api_key": "Enter Key",
            "default_language": "English",
            "text_model": "deepseek-ai/deepseek-v3.2-exp",
            "premium_text_model": "gpt-5-chat-latest",
            "vision_model": "zai-org/GLM-4.5V-FP8",
            "ocr_model": "zai-org/GLM-4.5V-FP8",
            "use_premium": False,
        }

        if os.path.exists(self.config_file):
            try:
                with open(self.config_file, 'r') as f:
                    loaded = json.load(f)
                    defaults.update(loaded)
            except:
                pass

        for key, value in defaults.items():
            setattr(self, key, value)

    def save(self):
        """Save configuration to file"""
        os.makedirs(self.config_dir, exist_ok=True)
        config_dict = {
            "api_url": self.api_url,
            "api_key": self.api_key,
            "default_language": self.default_language,
            "text_model": self.text_model,
            "premium_text_model": self.premium_text_model,
            "vision_model": self.vision_model,
            "ocr_model": self.ocr_model,
            "use_premium": self.use_premium,
        }
        with open(self.config_file, 'w') as f:
            json.dump(config_dict, f, indent=2)

class ProcessingDialog(Gtk.Window):
    """Dialog showing processing status with cancel button"""
    def __init__(self, title="Processing"):
        super().__init__(title=title)
        self.cancelled = False

        self.set_default_size(400, 150)
        self.set_position(Gtk.WindowPosition.CENTER)
        self.set_deletable(False)

        vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=15)
        vbox.set_margin_start(20)
        vbox.set_margin_end(20)
        vbox.set_margin_top(20)
        vbox.set_margin_bottom(20)
        self.add(vbox)

        # Status label
        self.status_label = Gtk.Label(label="Processing...")
        self.status_label.set_line_wrap(True)
        vbox.pack_start(self.status_label, False, False, 0)

        # Spinner
        self.spinner = Gtk.Spinner()
        self.spinner.start()
        vbox.pack_start(self.spinner, False, False, 0)

        # Cancel button
        cancel_button = Gtk.Button.new_with_label("Cancel")
        cancel_button.connect("clicked", self.on_cancel)
        vbox.pack_start(cancel_button, False, False, 0)

        self.show_all()

    def update_status(self, message):
        """Update status message"""
        self.status_label.set_text(message)

    def on_cancel(self, widget):
        """Handle cancel button"""
        self.cancelled = True
        self.destroy()

class MarkdownRenderer:
    """Simple Markdown to Pango markup converter"""

    @staticmethod
    def to_pango(markdown_text):
        """Convert markdown to Pango markup"""
        text = markdown_text

        # Escape existing markup
        text = GLib.markup_escape_text(text)

        # Headers (##, ###)
        text = re.sub(r'^### (.+)$', r'<b><big>\1</big></b>', text, flags=re.MULTILINE)
        text = re.sub(r'^## (.+)$', r'<b><span size="x-large">\1</span></b>', text, flags=re.MULTILINE)

        # Bold **text**
        text = re.sub(r'\*\*(.+?)\*\*', r'<b>\1</b>', text)

        # Italic *text*
        text = re.sub(r'\*(.+?)\*', r'<i>\1</i>', text)

        # Inline code `code`
        text = re.sub(r'`(.+?)`', r'<tt>\1</tt>', text)

        # Lists (simple version)
        lines = text.split('\n')
        result_lines = []
        for line in lines:
            if re.match(r'^\s*[-*]\s+', line):
                line = re.sub(r'^(\s*)[-*]\s+', r'\1• ', line)
            result_lines.append(line)
        text = '\n'.join(result_lines)

        return text

class ScreenshotConfirmDialog(Gtk.Window):
    """Dialog to confirm screenshot before sending to LLM"""
    def __init__(self, screenshot, operation_name, callback):
        super().__init__(title=f"Confirm {operation_name}")
        self.callback = callback
        self.screenshot = screenshot

        self.set_default_size(800, 600)
        self.set_position(Gtk.WindowPosition.CENTER)

        vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        vbox.set_margin_start(10)
        vbox.set_margin_end(10)
        vbox.set_margin_top(10)
        vbox.set_margin_bottom(10)
        self.add(vbox)

        # Info label
        info_label = Gtk.Label()
        info_label.set_markup(f"<b>Review the screenshot before sending to LLM:</b>")
        info_label.set_xalign(0)
        vbox.pack_start(info_label, False, False, 0)

        # Scrollable image preview
        scrolled = Gtk.ScrolledWindow()
        scrolled.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        scrolled.set_hexpand(True)
        scrolled.set_vexpand(True)

        # Convert PIL image to GdkPixbuf
        img_bytes = BytesIO()
        screenshot.save(img_bytes, format='PNG')
        img_bytes.seek(0)
        loader = GdkPixbuf.PixbufLoader.new_with_type('png')
        loader.write(img_bytes.read())
        loader.close()
        pixbuf = loader.get_pixbuf()

        # Scale image if too large for preview
        max_width = 780
        max_height = 500
        if pixbuf.get_width() > max_width or pixbuf.get_height() > max_height:
            scale = min(max_width / pixbuf.get_width(), max_height / pixbuf.get_height())
            new_width = int(pixbuf.get_width() * scale)
            new_height = int(pixbuf.get_height() * scale)
            pixbuf = pixbuf.scale_simple(new_width, new_height, GdkPixbuf.InterpType.BILINEAR)

        image = Gtk.Image.new_from_pixbuf(pixbuf)
        scrolled.add(image)
        vbox.pack_start(scrolled, True, True, 0)

        # Button box
        button_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)

        cancel_button = Gtk.Button.new_with_label("Cancel")
        cancel_button.connect("clicked", self.on_cancel)
        button_box.pack_start(cancel_button, False, False, 0)

        # Spacer
        button_box.pack_start(Gtk.Box(), True, True, 0)

        submit_button = Gtk.Button.new_with_label("Submit to LLM")
        submit_button.connect("clicked", self.on_submit)
        button_box.pack_end(submit_button, False, False, 0)

        vbox.pack_start(button_box, False, False, 0)

        self.show_all()
        submit_button.grab_focus()

    def on_cancel(self, widget):
        """Handle cancel"""
        self.screenshot.close()
        del self.screenshot
        self.destroy()

    def on_submit(self, widget):
        """Handle submit"""
        self.destroy()
        self.callback(self.screenshot)

class ClipboardConfirmDialog(Gtk.Window):
    """Dialog to confirm and optionally edit clipboard content before sending"""
    def __init__(self, clipboard_text, operation_name, callback):
        super().__init__(title=f"Confirm {operation_name}")
        self.callback = callback

        self.set_default_size(700, 500)
        self.set_position(Gtk.WindowPosition.CENTER)

        vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        vbox.set_margin_start(10)
        vbox.set_margin_end(10)
        vbox.set_margin_top(10)
        vbox.set_margin_bottom(10)
        self.add(vbox)

        # Info label
        info_label = Gtk.Label()
        info_label.set_markup(f"<b>Review and edit the text before sending to LLM:</b>")
        info_label.set_xalign(0)
        vbox.pack_start(info_label, False, False, 0)

        # Scrollable text view
        scrolled = Gtk.ScrolledWindow()
        scrolled.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        scrolled.set_hexpand(True)
        scrolled.set_vexpand(True)

        self.textview = Gtk.TextView()
        self.textview.set_wrap_mode(Gtk.WrapMode.WORD)
        self.textview.set_margin_start(5)
        self.textview.set_margin_end(5)
        self.textview.set_margin_top(5)
        self.textview.set_margin_bottom(5)
        self.textview.get_buffer().set_text(clipboard_text)

        scrolled.add(self.textview)
        vbox.pack_start(scrolled, True, True, 0)

        # Button box
        button_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)

        cancel_button = Gtk.Button.new_with_label("Cancel")
        cancel_button.connect("clicked", lambda w: self.destroy())
        button_box.pack_start(cancel_button, False, False, 0)

        # Spacer
        button_box.pack_start(Gtk.Box(), True, True, 0)

        submit_button = Gtk.Button.new_with_label("Submit")
        submit_button.connect("clicked", self.on_submit)
        button_box.pack_end(submit_button, False, False, 0)

        vbox.pack_start(button_box, False, False, 0)

        self.show_all()
        self.textview.grab_focus()

    def on_submit(self, widget):
        """Handle submit"""
        textbuffer = self.textview.get_buffer()
        start = textbuffer.get_start_iter()
        end = textbuffer.get_end_iter()
        text = textbuffer.get_text(start, end, False)

        self.destroy()
        self.callback(text)

class HotkeyManager:
    """Manage global hotkeys using python-xlib"""

    # Hotkey definitions: (modifiers, keysym, callback_name)
    HOTKEYS = [
        (X.ControlMask | X.ShiftMask, XK.XK_1, 'translate_text'),
        (X.ControlMask | X.ShiftMask, XK.XK_2, 'explain_text'),
        (X.ControlMask | X.ShiftMask, XK.XK_3, 'ocr_translate'),
        (X.ControlMask | X.ShiftMask, XK.XK_4, 'explain_image'),
        (X.ControlMask | X.ShiftMask, XK.XK_5, 'ocr_explain'),
        (X.ControlMask | X.ShiftMask, XK.XK_6, 'query_image'),
        (X.ControlMask | X.ShiftMask, XK.XK_7, 'query_text'),
    ]

    def __init__(self, callback_object):
        self.callback_object = callback_object
        self.display = display.Display()
        self.root = self.display.screen().root
        self.running = False
        self.hotkey_map = {}

    def setup_hotkeys(self):
        """Register all hotkeys"""
        for modifiers, keysym, callback_name in self.HOTKEYS:
            keycode = self.display.keysym_to_keycode(keysym)

            # Grab the key combination
            self.root.grab_key(
                keycode,
                modifiers,
                True,
                X.GrabModeAsync,
                X.GrabModeAsync
            )

            # Store mapping
            self.hotkey_map[(keycode, modifiers)] = callback_name

            print(f"Registered: Ctrl+Shift+{chr(XK.XK_1 + (keysym - XK.XK_1))} -> {callback_name}")

        self.display.sync()

    def start(self):
        """Start listening for hotkey events"""
        self.running = True
        thread = threading.Thread(target=self._event_loop, daemon=True)
        thread.start()

    def stop(self):
        """Stop listening for hotkey events"""
        self.running = False

    def _event_loop(self):
        """Main event loop for hotkey detection"""
        while self.running:
            try:
                # Check for events with timeout
                while self.display.pending_events():
                    event = self.display.next_event()

                    if event.type == X.KeyPress:
                        keycode = event.detail
                        modifiers = event.state & (X.ControlMask | X.ShiftMask | X.Mod1Mask | X.Mod4Mask)

                        # Look up callback
                        callback_name = self.hotkey_map.get((keycode, modifiers))
                        if callback_name:
                            # Call the callback in the main GTK thread
                            callback = getattr(self.callback_object, callback_name, None)
                            if callback:
                                GLib.idle_add(callback)

                # Small sleep to prevent CPU spinning
                time.sleep(0.01)

            except Exception as e:
                print(f"Hotkey error: {e}")
                time.sleep(0.1)

class SettingsDialog(Gtk.Dialog):
    """Settings dialog window"""
    def __init__(self, parent, config):
        super().__init__(title="LLM Assistant Settings", parent=parent, flags=0)
        self.add_buttons(
            Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL,
            Gtk.STOCK_OK, Gtk.ResponseType.OK
        )
        self.config = config
        self.set_default_size(500, 500)

        box = self.get_content_area()
        box.set_spacing(10)
        box.set_margin_start(10)
        box.set_margin_end(10)
        box.set_margin_top(10)
        box.set_margin_bottom(10)

        # API URL
        self.add_field(box, "API URL:", "api_url")

        # API Key
        self.add_field(box, "API Key:", "api_key")

        # Default Language
        self.add_field(box, "Default Language:", "default_language")

        # Models
        self.add_field(box, "Text Model:", "text_model")
        self.add_field(box, "Premium Text Model:", "premium_text_model")
        self.add_field(box, "Vision Model:", "vision_model")
        self.add_field(box, "OCR Model:", "ocr_model")

        # Add info label about hotkeys
        separator = Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL)
        box.pack_start(separator, False, False, 5)

        info_label = Gtk.Label()
        info_label.set_markup(
            "<b>Hotkeys:</b>\n"
            "Ctrl+Shift+1: Translate clipboard\n"
            "Ctrl+Shift+2: Explain clipboard\n"
            "Ctrl+Shift+3: OCR + Translate\n"
            "Ctrl+Shift+4: Explain image\n"
            "Ctrl+Shift+5: OCR + Explain\n"
            "Ctrl+Shift+6: Query image with custom prompt\n"
            "Ctrl+Shift+7: Query clipboard text with custom prompt"
        )
        info_label.set_xalign(0)
        box.pack_start(info_label, False, False, 0)

        self.show_all()

    def add_field(self, box, label_text, config_key):
        """Add a label and entry field"""
        hbox = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        label = Gtk.Label(label=label_text)
        label.set_width_chars(18)
        label.set_xalign(0)
        entry = Gtk.Entry()
        entry.set_text(str(getattr(self.config, config_key)))
        entry.set_hexpand(True)
        setattr(self, f"entry_{config_key}", entry)
        hbox.pack_start(label, False, False, 0)
        hbox.pack_start(entry, True, True, 0)
        box.pack_start(hbox, False, False, 0)

    def get_values(self):
        """Get values from entries"""
        return {
            "api_url": self.entry_api_url.get_text(),
            "api_key": self.entry_api_key.get_text(),
            "default_language": self.entry_default_language.get_text(),
            "text_model": self.entry_text_model.get_text(),
            "premium_text_model": self.entry_premium_text_model.get_text(),
            "vision_model": self.entry_vision_model.get_text(),
            "ocr_model": self.entry_ocr_model.get_text(),
        }

class TextQueryDialog(Gtk.Window):
    """Dialog for querying clipboard text with custom prompt"""
    def __init__(self, clipboard_text, callback):
        super().__init__(title="Query Text")
        self.callback = callback
        self.clipboard_text = clipboard_text

        self.set_default_size(800, 600)
        self.set_position(Gtk.WindowPosition.CENTER)

        # Main vertical box
        vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        vbox.set_margin_start(10)
        vbox.set_margin_end(10)
        vbox.set_margin_top(10)
        vbox.set_margin_bottom(10)
        self.add(vbox)

        # Label for clipboard text
        text_label = Gtk.Label(label="Clipboard Text:")
        text_label.set_xalign(0)
        vbox.pack_start(text_label, False, False, 0)

        # Scrollable text view showing clipboard content
        scrolled_clipboard = Gtk.ScrolledWindow()
        scrolled_clipboard.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        scrolled_clipboard.set_min_content_height(200)

        clipboard_textview = Gtk.TextView()
        clipboard_textview.set_editable(False)
        clipboard_textview.set_wrap_mode(Gtk.WrapMode.WORD)
        clipboard_textview.set_margin_start(5)
        clipboard_textview.set_margin_end(5)
        clipboard_textview.set_margin_top(5)
        clipboard_textview.set_margin_bottom(5)
        clipboard_textview.get_buffer().set_text(clipboard_text)

        scrolled_clipboard.add(clipboard_textview)
        vbox.pack_start(scrolled_clipboard, True, True, 0)

        # Separator
        separator = Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL)
        vbox.pack_start(separator, False, False, 5)

        # Query options label
        query_label = Gtk.Label(label="Select a question or enter your own:")
        query_label.set_xalign(0)
        vbox.pack_start(query_label, False, False, 0)

        # Radio buttons for preset queries
        self.radio_summarize = Gtk.RadioButton.new_with_label_from_widget(
            None, "Summarize the provided text."
        )
        vbox.pack_start(self.radio_summarize, False, False, 0)

        self.radio_explain = Gtk.RadioButton.new_with_label_from_widget(
            self.radio_summarize, "Explain the text concisely and simply."
        )
        vbox.pack_start(self.radio_explain, False, False, 0)

        self.radio_accuracy = Gtk.RadioButton.new_with_label_from_widget(
            self.radio_summarize, "Tell me if this information is accurate and why or why not?"
        )
        vbox.pack_start(self.radio_accuracy, False, False, 0)

        self.radio_custom = Gtk.RadioButton.new_with_label_from_widget(
            self.radio_summarize, "Custom question:"
        )
        vbox.pack_start(self.radio_custom, False, False, 0)

        # Custom query text entry
        scrolled_custom = Gtk.ScrolledWindow()
        scrolled_custom.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        scrolled_custom.set_min_content_height(80)

        self.custom_textview = Gtk.TextView()
        self.custom_textview.set_wrap_mode(Gtk.WrapMode.WORD)
        self.custom_textview.set_margin_start(5)
        self.custom_textview.set_margin_end(5)
        self.custom_textview.set_margin_top(5)
        self.custom_textview.set_margin_bottom(5)
        scrolled_custom.add(self.custom_textview)

        vbox.pack_start(scrolled_custom, False, False, 0)

        # Connect custom text view focus to select custom radio button
        self.custom_textview.connect("focus-in-event", lambda w, e: self.radio_custom.set_active(True))

        # Button box
        button_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)

        cancel_button = Gtk.Button.new_with_label("Cancel")
        cancel_button.connect("clicked", lambda w: self.destroy())
        button_box.pack_start(cancel_button, False, False, 0)

        # Spacer
        button_box.pack_start(Gtk.Box(), True, True, 0)

        submit_button = Gtk.Button.new_with_label("Submit Query")
        submit_button.connect("clicked", self.on_submit)
        button_box.pack_end(submit_button, False, False, 0)

        vbox.pack_start(button_box, False, False, 0)

        self.show_all()
        self.radio_summarize.grab_focus()

    def on_submit(self, widget):
        """Handle submit button"""
        # Determine which query to use
        if self.radio_summarize.get_active():
            query = "Summarize the provided text."
        elif self.radio_explain.get_active():
            query = "Explain the text concisely and simply."
        elif self.radio_accuracy.get_active():
            query = "Tell me if this information is accurate and why or why not?"
        else:  # custom
            textbuffer = self.custom_textview.get_buffer()
            start = textbuffer.get_start_iter()
            end = textbuffer.get_end_iter()
            query = textbuffer.get_text(start, end, False).strip()

            if not query:
                # Show error dialog
                dialog = Gtk.MessageDialog(
                    parent=self,
                    flags=0,
                    message_type=Gtk.MessageType.WARNING,
                    buttons=Gtk.ButtonsType.OK,
                    text="Please enter a custom question or select a preset option"
                )
                dialog.run()
                dialog.destroy()
                return

        self.destroy()
        self.callback(self.clipboard_text, query)

class ImageQueryDialog(Gtk.Window):
    """Dialog for querying an image with custom prompt"""
    def __init__(self, screenshot, callback):
        super().__init__(title="Query Image")
        self.callback = callback
        self.screenshot = screenshot

        self.set_default_size(800, 600)
        self.set_position(Gtk.WindowPosition.CENTER)

        # Main vertical box
        vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        vbox.set_margin_start(10)
        vbox.set_margin_end(10)
        vbox.set_margin_top(10)
        vbox.set_margin_bottom(10)
        self.add(vbox)

        # Image preview (scrollable)
        scrolled_img = Gtk.ScrolledWindow()
        scrolled_img.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        scrolled_img.set_min_content_height(300)

        # Convert PIL image to GdkPixbuf
        img_bytes = BytesIO()
        screenshot.save(img_bytes, format='PNG')
        img_bytes.seek(0)
        loader = GdkPixbuf.PixbufLoader.new_with_type('png')
        loader.write(img_bytes.read())
        loader.close()
        pixbuf = loader.get_pixbuf()

        # Scale image if too large
        max_width = 780
        max_height = 400
        if pixbuf.get_width() > max_width or pixbuf.get_height() > max_height:
            # Calculate scaling to fit within bounds while maintaining aspect ratio
            scale = min(max_width / pixbuf.get_width(), max_height / pixbuf.get_height())
            new_width = int(pixbuf.get_width() * scale)
            new_height = int(pixbuf.get_height() * scale)
            pixbuf = pixbuf.scale_simple(new_width, new_height, GdkPixbuf.InterpType.BILINEAR)

        image = Gtk.Image.new_from_pixbuf(pixbuf)
        scrolled_img.add(image)

        vbox.pack_start(scrolled_img, True, True, 0)

        # Prompt label
        prompt_label = Gtk.Label(label="Enter your question about this image:")
        prompt_label.set_xalign(0)
        vbox.pack_start(prompt_label, False, False, 0)

        # Text entry for prompt
        scrolled_text = Gtk.ScrolledWindow()
        scrolled_text.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        scrolled_text.set_min_content_height(80)

        self.textview = Gtk.TextView()
        self.textview.set_wrap_mode(Gtk.WrapMode.WORD)
        self.textview.set_margin_start(5)
        self.textview.set_margin_end(5)
        self.textview.set_margin_top(5)
        self.textview.set_margin_bottom(5)
        scrolled_text.add(self.textview)

        vbox.pack_start(scrolled_text, False, False, 0)

        # Button box
        button_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)

        cancel_button = Gtk.Button.new_with_label("Cancel")
        cancel_button.connect("clicked", lambda w: self.destroy())
        button_box.pack_start(cancel_button, False, False, 0)

        # Spacer
        button_box.pack_start(Gtk.Box(), True, True, 0)

        submit_button = Gtk.Button.new_with_label("Submit Query")
        submit_button.connect("clicked", self.on_submit)
        button_box.pack_end(submit_button, False, False, 0)

        vbox.pack_start(button_box, False, False, 0)

        self.show_all()
        self.textview.grab_focus()

    def on_submit(self, widget):
        """Handle submit button"""
        textbuffer = self.textview.get_buffer()
        start = textbuffer.get_start_iter()
        end = textbuffer.get_end_iter()
        user_query = textbuffer.get_text(start, end, False).strip()

        if user_query:
            self.destroy()
            self.callback(self.screenshot, user_query)
        else:
            # Show error dialog
            dialog = Gtk.MessageDialog(
                parent=self,
                flags=0,
                message_type=Gtk.MessageType.WARNING,
                buttons=Gtk.ButtonsType.OK,
                text="Please enter a question"
            )
            dialog.run()
            dialog.destroy()

class ScreenSelector(Gtk.Window):
    """Full-screen overlay for selecting screen region across all monitors"""
    def __init__(self, callback):
        super().__init__()
        self.callback = callback
        self.start_x = None
        self.start_y = None
        self.end_x = None
        self.end_y = None

        # Get the display and screen to calculate total geometry
        self.gdk_display = Gdk.Display.get_default()

        # Calculate total screen geometry across all monitors
        self.total_geometry = self._calculate_total_geometry()

        # Make window cover all monitors
        self.set_decorated(False)
        self.set_app_paintable(True)
        self.set_keep_above(True)

        # Position and size to cover all monitors
        self.move(self.total_geometry['x'], self.total_geometry['y'])
        self.set_default_size(self.total_geometry['width'], self.total_geometry['height'])

        # Set up transparency
        screen = self.get_screen()
        visual = screen.get_rgba_visual()
        if visual:
            self.set_visual(visual)

        # Drawing area
        self.drawing_area = Gtk.DrawingArea()
        self.drawing_area.connect('draw', self.on_draw)
        self.add(self.drawing_area)

        # Mouse events
        self.drawing_area.set_events(
            Gdk.EventMask.BUTTON_PRESS_MASK |
            Gdk.EventMask.BUTTON_RELEASE_MASK |
            Gdk.EventMask.POINTER_MOTION_MASK
        )
        self.drawing_area.connect('button-press-event', self.on_button_press)
        self.drawing_area.connect('button-release-event', self.on_button_release)
        self.drawing_area.connect('motion-notify-event', self.on_motion)

        # ESC to cancel
        self.connect('key-press-event', self.on_key_press)

        self.show_all()

        # Make sure window grabs focus and input
        self.present()
        self.grab_focus()

    def _calculate_total_geometry(self):
        """Calculate the bounding box that covers all monitors"""
        min_x = float('inf')
        min_y = float('inf')
        max_x = float('-inf')
        max_y = float('-inf')

        n_monitors = self.gdk_display.get_n_monitors()

        for i in range(n_monitors):
            monitor = self.gdk_display.get_monitor(i)
            geometry = monitor.get_geometry()

            min_x = min(min_x, geometry.x)
            min_y = min(min_y, geometry.y)
            max_x = max(max_x, geometry.x + geometry.width)
            max_y = max(max_y, geometry.y + geometry.height)

        total = {
            'x': int(min_x),
            'y': int(min_y),
            'width': int(max_x - min_x),
            'height': int(max_y - min_y)
        }

        return total

    def on_draw(self, widget, cr):
        """Draw semi-transparent overlay and selection rectangle"""
        # Semi-transparent background
        cr.set_source_rgba(0, 0, 0, 0.3)
        cr.paint()

        # Draw selection rectangle if dragging
        if self.start_x is not None and self.end_x is not None:
            # Convert window coordinates to absolute screen coordinates
            x = min(self.start_x, self.end_x)
            y = min(self.start_y, self.end_y)
            w = abs(self.end_x - self.start_x)
            h = abs(self.end_y - self.start_y)

            # Clear rectangle (make it see-through)
            cr.set_operator(1)  # CLEAR
            cr.rectangle(x, y, w, h)
            cr.fill()

            # Draw border
            cr.set_operator(0)  # OVER
            cr.set_source_rgba(1, 0, 0, 0.8)
            cr.set_line_width(2)
            cr.rectangle(x, y, w, h)
            cr.stroke()

    def on_button_press(self, widget, event):
        """Start selection"""
        self.start_x = event.x
        self.start_y = event.y
        self.end_x = event.x
        self.end_y = event.y

    def on_motion(self, widget, event):
        """Update selection"""
        if self.start_x is not None:
            self.end_x = event.x
            self.end_y = event.y
            self.queue_draw()

    def on_button_release(self, widget, event):
        """Finish selection"""
        self.end_x = event.x
        self.end_y = event.y

        # Convert window-relative coordinates to absolute screen coordinates
        window = self.get_window()
        window_x, window_y = window.get_origin()[1], window.get_origin()[2]

        # Calculate selection in absolute screen coordinates
        abs_start_x = window_x + int(self.start_x)
        abs_start_y = window_y + int(self.start_y)
        abs_end_x = window_x + int(self.end_x)
        abs_end_y = window_y + int(self.end_y)

        x = min(abs_start_x, abs_end_x)
        y = min(abs_start_y, abs_end_y)
        w = abs(abs_end_x - abs_start_x)
        h = abs(abs_end_y - abs_start_y)

        self.destroy()

        if w > 10 and h > 10:  # Minimum size
            self.callback(x, y, w, h)

    def on_key_press(self, widget, event):
        """Cancel on ESC"""
        if event.keyval == Gdk.KEY_Escape:
            self.destroy()

class LLMAssistant:
    """Main application"""
    def __init__(self):
        self.config = Config()
        self.hotkey_manager = None
        self.premium_toggle_item = None

        # Create indicator
        self.indicator = AppIndicator3.Indicator.new(
            "llm-assistant",
            "edit-paste",  # Icon name from theme
            AppIndicator3.IndicatorCategory.APPLICATION_STATUS
        )
        self.indicator.set_status(AppIndicator3.IndicatorStatus.ACTIVE)

        # Create menu
        self.create_menu()

        # Setup hotkeys
        self.setup_hotkeys()

    def create_menu(self):
        """Create the system tray menu"""
        menu = Gtk.Menu()

        # Premium model toggle
        self.premium_toggle_item = Gtk.CheckMenuItem(label="Use Premium Text Model")
        self.premium_toggle_item.set_active(self.config.use_premium)
        self.premium_toggle_item.connect("toggled", self.toggle_premium_model)
        menu.append(self.premium_toggle_item)

        menu.append(Gtk.SeparatorMenuItem())

        item_settings = Gtk.MenuItem(label="Settings")
        item_settings.connect("activate", self.show_settings)
        menu.append(item_settings)

        menu.append(Gtk.SeparatorMenuItem())

        # Add manual trigger items for testing
        item_translate = Gtk.MenuItem(label="Translate Clipboard (Ctrl+Shift+1)")
        item_translate.connect("activate", lambda w: self.translate_text())
        menu.append(item_translate)

        item_explain = Gtk.MenuItem(label="Explain Clipboard (Ctrl+Shift+2)")
        item_explain.connect("activate", lambda w: self.explain_text())
        menu.append(item_explain)

        item_ocr_trans = Gtk.MenuItem(label="OCR + Translate (Ctrl+Shift+3)")
        item_ocr_trans.connect("activate", lambda w: self.ocr_translate())
        menu.append(item_ocr_trans)

        item_img_explain = Gtk.MenuItem(label="Explain Image (Ctrl+Shift+4)")
        item_img_explain.connect("activate", lambda w: self.explain_image())
        menu.append(item_img_explain)

        item_ocr_explain = Gtk.MenuItem(label="OCR + Explain (Ctrl+Shift+5)")
        item_ocr_explain.connect("activate", lambda w: self.ocr_explain())
        menu.append(item_ocr_explain)

        item_query = Gtk.MenuItem(label="Query Image (Ctrl+Shift+6)")
        item_query.connect("activate", lambda w: self.query_image())
        menu.append(item_query)

        item_query_text = Gtk.MenuItem(label="Query Text (Ctrl+Shift+7)")
        item_query_text.connect("activate", lambda w: self.query_text())
        menu.append(item_query_text)

        menu.append(Gtk.SeparatorMenuItem())

        item_quit = Gtk.MenuItem(label="Quit")
        item_quit.connect("activate", self.quit)
        menu.append(item_quit)

        menu.show_all()
        self.indicator.set_menu(menu)

    def toggle_premium_model(self, widget):
        """Toggle between standard and premium text model"""
        self.config.use_premium = widget.get_active()
        self.config.save()

        model_name = self.config.premium_text_model if self.config.use_premium else self.config.text_model
        status = "enabled" if self.config.use_premium else "disabled"
        self.show_notification(f"Premium model {status}: {model_name}")

    def get_active_text_model(self):
        """Get the currently active text model based on toggle setting"""
        return self.config.premium_text_model if self.config.use_premium else self.config.text_model

    def setup_hotkeys(self):
        """Setup global hotkeys"""
        try:
            self.hotkey_manager = HotkeyManager(self)
            self.hotkey_manager.setup_hotkeys()
            self.hotkey_manager.start()
            print("Global hotkeys enabled")
        except Exception as e:
            print(f"Warning: Could not setup hotkeys: {e}")
            print("You can still use the menu items")

    def show_settings(self, widget):
        """Show settings dialog"""
        dialog = SettingsDialog(None, self.config)
        response = dialog.run()

        if response == Gtk.ResponseType.OK:
            values = dialog.get_values()
            for key, value in values.items():
                setattr(self.config, key, value)
            self.config.save()
            self.show_notification("Settings saved")

        dialog.destroy()

    def show_notification(self, message):
        """Show desktop notification"""
        try:
            subprocess.run(['notify-send', '--urgency=low', '--hint=int:transient:1', 'LLM Assistant', message])
        except:
            print(f"Notification: {message}")

    def get_clipboard_text(self):
        """Get text from clipboard"""
        clipboard = Gtk.Clipboard.get(Gdk.SELECTION_CLIPBOARD)
        text = clipboard.wait_for_text()

        # Check if clipboard contains text
        if text is None:
            # Try to check if it's an image or file
            if clipboard.wait_is_image_available():
                return None, "image"
            elif clipboard.wait_is_uris_available():
                return None, "file"
            else:
                return None, "empty"

        return text, "text"

    def call_llm_streaming(self, model, messages, image_base64, progress_dialog):
        """Call LLM API with streaming support (for text-only operations)"""
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.config.api_key}"
        }

        data = {
            "model": model,
            "messages": messages,
            "stream": True
        }

        try:
            response = requests.post(
                self.config.api_url,
                headers=headers,
                json=data,
                stream=True,
                timeout=10
            )
            response.raise_for_status()

            result_text = ""
            for line in response.iter_lines():
                if progress_dialog.cancelled:
                    return None

                if line:
                    line = line.decode('utf-8')
                    if line.startswith('data: '):
                        line = line[6:]
                        if line.strip() == '[DONE]':
                            break
                        try:
                            chunk = json.loads(line)
                            if 'choices' in chunk and len(chunk['choices']) > 0:
                                delta = chunk['choices'][0].get('delta', {})
                                content = delta.get('content', '')
                                if content:
                                    result_text += content
                                    GLib.idle_add(progress_dialog.update_status, 
                                                f"Receiving response... ({len(result_text)} chars)")
                        except json.JSONDecodeError:
                            pass

            return result_text if result_text else "No response received"

        except requests.exceptions.Timeout:
            return "Error: Connection timeout"
        except Exception as e:
            return f"Error: {str(e)}"

    def call_llm(self, model, messages, image_base64=None):
        """Call LLM API without streaming (for image operations)"""
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.config.api_key}"
        }

        # Prepare messages  
        if image_base64:
            messages[0]["content"] = [
                {"type": "text", "text": messages[0]["content"]},
                {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{image_base64}"}}
            ]

        data = {
            "model": model,
            "messages": messages,
            "stream": False
        }

        try:
            response = requests.post(
                self.config.api_url,
                headers=headers,
                json=data,
                timeout=120
            )
            response.raise_for_status()
            result = response.json()
            return result['choices'][0]['message']['content']
        except Exception as e:
            return f"Error: {str(e)}"

    def translate_text(self, widget=None):
        """Ctrl+Shift+1: Translate clipboard text"""
        text, content_type = self.get_clipboard_text()

        if content_type != "text":
            if content_type == "image":
                self.show_notification("Clipboard contains an image, not text")
            elif content_type == "file":
                self.show_notification("Clipboard contains a file, not text")
            else:
                self.show_notification("Clipboard does not contain text")
            return

        # Show confirmation dialog
        ClipboardConfirmDialog(text, "Translation", self._process_translate)

    def _process_translate(self, text):
        """Process translation after confirmation"""
        progress_dialog = ProcessingDialog("Translating")

        def process():
            messages = [{
                "role": "user",
                "content": f"Translate the following text to {self.config.default_language}. Respond in Markdown format. Only provide the translation, no explanations:\n\n{text}"
            }]
            result = self.call_llm_streaming(self.get_active_text_model(), messages, None, progress_dialog)

            if not progress_dialog.cancelled and result:
                GLib.idle_add(progress_dialog.destroy)
                GLib.idle_add(self.show_result, "Translation", result)
            elif progress_dialog.cancelled:
                GLib.idle_add(progress_dialog.destroy)

        threading.Thread(target=process, daemon=True).start()

    def explain_text(self, widget=None):
        """Ctrl+Shift+2: Explain clipboard text"""
        text, content_type = self.get_clipboard_text()

        if content_type != "text":
            if content_type == "image":
                self.show_notification("Clipboard contains an image, not text")
            elif content_type == "file":
                self.show_notification("Clipboard contains a file, not text")
            else:
                self.show_notification("Clipboard does not contain text")
            return

        # Show confirmation dialog
        ClipboardConfirmDialog(text, "Explanation", self._process_explain)

    def _process_explain(self, text):
        """Process explanation after confirmation"""
        progress_dialog = ProcessingDialog("Getting Explanation")

        def process():
            messages = [{
                "role": "user",
                "content": f"Provide more information and context about the following text. Respond in {self.config.default_language} using Markdown format:\n\n{text}"
            }]
            result = self.call_llm_streaming(self.get_active_text_model(), messages, None, progress_dialog)

            if not progress_dialog.cancelled and result:
                GLib.idle_add(progress_dialog.destroy)
                GLib.idle_add(self.show_result, "Explanation", result)
            elif progress_dialog.cancelled:
                GLib.idle_add(progress_dialog.destroy)

        threading.Thread(target=process, daemon=True).start()

    def ocr_translate(self, widget=None):
        """Ctrl+Shift+3: OCR + Translate"""
        self.show_notification("Select screen area...")
        ScreenSelector(self._ocr_translate_screenshot_callback)

    def _ocr_translate_screenshot_callback(self, x, y, w, h):
        """Show confirmation dialog for screenshot"""
        screenshot = ImageGrab.grab(bbox=(x, y, x+w, y+h))
        ScreenshotConfirmDialog(screenshot, "OCR + Translation", self._ocr_translate_callback)

    def _ocr_translate_callback(self, screenshot_param):
        """Process OCR + Translation after confirmation"""
        progress_dialog = ProcessingDialog("OCR + Translation")

        # Convert to base64 BEFORE starting thread
        buffered = BytesIO()
        screenshot_param.save(buffered, format="PNG")
        img_base64 = base64.b64encode(buffered.getvalue()).decode()

        # Clear screenshot from memory
        screenshot_param.close()
        del screenshot_param

        def process():
            GLib.idle_add(progress_dialog.update_status, "Extracting text from image...")

            if progress_dialog.cancelled:
                GLib.idle_add(progress_dialog.destroy)
                return

            # OCR
            ocr_messages = [{
                "role": "user",
                "content": "Extract all text from this image. Only provide the extracted text, no explanations."
            }]
            ocr_result = self.call_llm(self.config.ocr_model, ocr_messages, img_base64)

            if progress_dialog.cancelled:
                GLib.idle_add(progress_dialog.destroy)
                return

            GLib.idle_add(progress_dialog.update_status, "Translating text...")

            # Translate
            translate_messages = [{
                "role": "user",
                "content": f"Translate the following text to {self.config.default_language}. Respond in Markdown format. Only provide the translation:\n\n{ocr_result}"
            }]
            final_result = self.call_llm_streaming(self.get_active_text_model(), translate_messages, None, progress_dialog)

            if not progress_dialog.cancelled and final_result:
                GLib.idle_add(progress_dialog.destroy)
                GLib.idle_add(self.show_result, "OCR + Translation", final_result)
            elif progress_dialog.cancelled:
                GLib.idle_add(progress_dialog.destroy)

        threading.Thread(target=process, daemon=True).start()

    def explain_image(self, widget=None):
        """Ctrl+Shift+4: Explain image"""
        self.show_notification("Select screen area...")
        ScreenSelector(self._explain_image_screenshot_callback)

    def _explain_image_screenshot_callback(self, x, y, w, h):
        """Show confirmation dialog for screenshot"""
        screenshot = ImageGrab.grab(bbox=(x, y, x+w, y+h))
        ScreenshotConfirmDialog(screenshot, "Image Analysis", self._explain_image_callback)

    def _explain_image_callback(self, screenshot_param):
        """Process image explanation after confirmation"""
        progress_dialog = ProcessingDialog("Analyzing Image")

        # Convert to base64 BEFORE starting thread
        buffered = BytesIO()
        screenshot_param.save(buffered, format="PNG")
        img_base64 = base64.b64encode(buffered.getvalue()).decode()

        # Clear from memory
        screenshot_param.close()
        del screenshot_param

        def process():
            GLib.idle_add(progress_dialog.update_status, "Analyzing image...")

            if progress_dialog.cancelled:
                GLib.idle_add(progress_dialog.destroy)
                return

            messages = [{
                "role": "user",
                "content": f"Describe and explain what you see in this image. Provide detailed information. Respond in {self.config.default_language} using Markdown format."
            }]
            result = self.call_llm(self.config.vision_model, messages, img_base64)

            if not progress_dialog.cancelled and result:
                GLib.idle_add(progress_dialog.destroy)
                GLib.idle_add(self.show_result, "Image Analysis", result)
            elif progress_dialog.cancelled:
                GLib.idle_add(progress_dialog.destroy)

        threading.Thread(target=process, daemon=True).start()

    def ocr_explain(self, widget=None):
        """Ctrl+Shift+5: OCR + Explain"""
        self.show_notification("Select screen area...")
        ScreenSelector(self._ocr_explain_screenshot_callback)

    def _ocr_explain_screenshot_callback(self, x, y, w, h):
        """Show confirmation dialog for screenshot"""
        screenshot = ImageGrab.grab(bbox=(x, y, x+w, y+h))
        ScreenshotConfirmDialog(screenshot, "OCR + Explanation", self._ocr_explain_callback)

    def _ocr_explain_callback(self, screenshot_param):
        """Process OCR + Explanation after confirmation"""
        progress_dialog = ProcessingDialog("OCR + Explanation")

        # Convert to base64 BEFORE starting thread
        buffered = BytesIO()
        screenshot_param.save(buffered, format="PNG")
        img_base64 = base64.b64encode(buffered.getvalue()).decode()

        screenshot_param.close()
        del screenshot_param

        def process():
            GLib.idle_add(progress_dialog.update_status, "Extracting text from image...")

            if progress_dialog.cancelled:
                GLib.idle_add(progress_dialog.destroy)
                return

            # OCR
            ocr_messages = [{
                "role": "user",
                "content": "Extract all text from this image. Only provide the extracted text."
            }]
            ocr_result = self.call_llm(self.config.ocr_model, ocr_messages, img_base64)

            if progress_dialog.cancelled:
                GLib.idle_add(progress_dialog.destroy)
                return

            GLib.idle_add(progress_dialog.update_status, "Generating explanation...")

            # Explain
            explain_messages = [{
                "role": "user",
                "content": f"Provide more information and context about the following text. Respond in {self.config.default_language} using Markdown format:\n\n{ocr_result}"
            }]
            final_result = self.call_llm_streaming(self.get_active_text_model(), explain_messages, None, progress_dialog)

            if not progress_dialog.cancelled and final_result:
                GLib.idle_add(progress_dialog.destroy)
                GLib.idle_add(self.show_result, "OCR + Explanation", final_result)
            elif progress_dialog.cancelled:
                GLib.idle_add(progress_dialog.destroy)

        threading.Thread(target=process, daemon=True).start()

    def query_image(self, widget=None):
        """Ctrl+Shift+6: Query image with custom prompt"""
        self.show_notification("Select screen area...")
        ScreenSelector(self._query_image_callback)

    def _query_image_callback(self, x, y, w, h):
        """Show prompt dialog for image query"""
        screenshot = ImageGrab.grab(bbox=(x, y, x+w, y+h))
        ImageQueryDialog(screenshot, self._process_query_image)

    def _process_query_image(self, screenshot_param, user_query):
        """Process image query with user's custom prompt"""
        progress_dialog = ProcessingDialog("Processing Query")

        # Convert to base64 BEFORE starting thread
        buffered = BytesIO()
        screenshot_param.save(buffered, format="PNG")
        img_base64 = base64.b64encode(buffered.getvalue()).decode()

        screenshot_param.close()
        del screenshot_param

        def process():
            GLib.idle_add(progress_dialog.update_status, "Extracting text from image...")

            if progress_dialog.cancelled:
                GLib.idle_add(progress_dialog.destroy)
                return

            # Step 1: OCR
            ocr_messages = [{
                "role": "user",
                "content": "Extract all text from this image. Only provide the extracted text, no explanations. If there is no text, respond with 'No text found'."
            }]
            ocr_result = self.call_llm(self.config.ocr_model, ocr_messages, img_base64)

            if progress_dialog.cancelled:
                GLib.idle_add(progress_dialog.destroy)
                return

            GLib.idle_add(progress_dialog.update_status, "Analyzing image visually...")

            # Step 2: Vision
            vision_messages = [{
                "role": "user",
                "content": "Describe what you see in this image in detail. Focus on the main elements, layout, and visual characteristics."
            }]
            vision_result = self.call_llm(self.config.vision_model, vision_messages, img_base64)

            if progress_dialog.cancelled:
                GLib.idle_add(progress_dialog.destroy)
                return

            GLib.idle_add(progress_dialog.update_status, "Generating answer...")

            # Step 3: Combine and answer
            combined_prompt = f"""You are analyzing an image for a user. Here is the information extracted from the image:

TEXT EXTRACTED FROM IMAGE:
{ocr_result}

VISUAL DESCRIPTION OF IMAGE:
{vision_result}

USER'S QUESTION:
{user_query}

Please answer the user's question based on both the extracted text and visual description of the image. Respond in {self.config.default_language} using Markdown format."""

            query_messages = [{
                "role": "user",
                "content": combined_prompt
            }]
            final_result = self.call_llm_streaming(self.get_active_text_model(), query_messages, None, progress_dialog)

            if not progress_dialog.cancelled and final_result:
                GLib.idle_add(progress_dialog.destroy)
                GLib.idle_add(self.show_result, "Query Result", final_result)
            elif progress_dialog.cancelled:
                GLib.idle_add(progress_dialog.destroy)

        threading.Thread(target=process, daemon=True).start()

    def query_text(self, widget=None):
        """Ctrl+Shift+7: Query clipboard text with custom prompt"""
        text, content_type = self.get_clipboard_text()

        if content_type != "text":
            if content_type == "image":
                self.show_notification("Clipboard contains an image, not text")
            elif content_type == "file":
                self.show_notification("Clipboard contains a file, not text")
            else:
                self.show_notification("Clipboard does not contain text")
            return

        TextQueryDialog(text, self._process_query_text)

    def _process_query_text(self, clipboard_text, user_query):
        """Process text query with user's custom prompt"""
        progress_dialog = ProcessingDialog("Processing Query")

        def process():
            combined_prompt = f"""Here is some text that the user has provided:

TEXT:
{clipboard_text}

USER'S QUESTION:
{user_query}

Please answer the user's question based on the provided text. Respond in {self.config.default_language} using Markdown format."""

            messages = [{
                "role": "user",
                "content": combined_prompt
            }]
            result = self.call_llm_streaming(self.get_active_text_model(), messages, None, progress_dialog)

            if not progress_dialog.cancelled and result:
                GLib.idle_add(progress_dialog.destroy)
                GLib.idle_add(self.show_result, "Query Result", result)
            elif progress_dialog.cancelled:
                GLib.idle_add(progress_dialog.destroy)

        threading.Thread(target=process, daemon=True).start()

    def show_result(self, title, markdown_text):
        """Show result in a custom dialog with Markdown rendering"""
        # Create a regular window
        dialog = Gtk.Window(title=title)
        dialog.set_default_size(700, 500)
        dialog.set_position(Gtk.WindowPosition.CENTER)

        # Main vertical box
        vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        dialog.add(vbox)

        # Scrolled window with text view
        scrolled = Gtk.ScrolledWindow()
        scrolled.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        scrolled.set_hexpand(True)
        scrolled.set_vexpand(True)

        textview = Gtk.TextView()
        textview.set_editable(False)
        textview.set_wrap_mode(Gtk.WrapMode.WORD)
        textview.set_margin_start(15)
        textview.set_margin_end(15)
        textview.set_margin_top(15)
        textview.set_margin_bottom(15)
        textview.set_left_margin(10)
        textview.set_right_margin(10)

        # Use monospace font for code blocks
        font_desc = Pango.FontDescription("Monospace 10")
        textview.modify_font(font_desc)

        textbuffer = textview.get_buffer()

        # Try to render as Pango markup for simple markdown
        try:
            pango_markup = MarkdownRenderer.to_pango(markdown_text)
            textbuffer.insert_markup(textbuffer.get_start_iter(), pango_markup, -1)
        except:
            # Fallback to plain text if markup fails
            textbuffer.set_text(markdown_text)

        scrolled.add(textview)
        vbox.pack_start(scrolled, True, True, 0)

        # Button box at bottom
        button_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        button_box.set_margin_start(10)
        button_box.set_margin_end(10)
        button_box.set_margin_top(10)
        button_box.set_margin_bottom(10)

        # Copy button
        copy_button = Gtk.Button.new_with_label("Copy to Clipboard")
        copy_button.connect("clicked", lambda w: self._copy_to_clipboard(markdown_text))
        button_box.pack_start(copy_button, False, False, 0)

        # Spacer
        button_box.pack_start(Gtk.Box(), True, True, 0)

        # Close button
        close_button = Gtk.Button.new_with_label("Close")
        close_button.connect("clicked", lambda w: dialog.destroy())
        button_box.pack_end(close_button, False, False, 0)

        vbox.pack_start(button_box, False, False, 0)

        # Show everything
        dialog.show_all()

        # Make close button focused by default
        close_button.grab_focus()

    def _copy_to_clipboard(self, text):
        """Copy text to clipboard"""
        clipboard = Gtk.Clipboard.get(Gdk.SELECTION_CLIPBOARD)
        clipboard.set_text(text, -1)
        clipboard.store()
        self.show_notification("Copied to clipboard")

    def quit(self, widget):
        """Quit application"""
        if self.hotkey_manager:
            self.hotkey_manager.stop()
        Gtk.main_quit()

    def run(self):
        """Run the application"""
        print("\n" + "=" * 60)
        print("LLM Assistant Started")
        print("=" * 60)
        print("\nGlobal Hotkeys:")
        print("  Ctrl+Shift+1 - Translate clipboard text")
        print("  Ctrl+Shift+2 - Explain clipboard text")
        print("  Ctrl+Shift+3 - OCR + Translate screenshot")
        print("  Ctrl+Shift+4 - Explain screenshot")
        print("  Ctrl+Shift+5 - OCR + Explain screenshot")
        print("  Ctrl+Shift+6 - Query screenshot with custom prompt")
        print("  Ctrl+Shift+7 - Query clipboard text with custom prompt")
        print("\nCheck system tray for menu and settings")
        print("=" * 60 + "\n")

        Gtk.main()

if __name__ == "__main__":
    app = LLMAssistant()
    app.run()
