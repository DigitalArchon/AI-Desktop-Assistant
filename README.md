# AI-Desktop-Assistant
A simple python tool that allows quick AI lookups of text or screen grabs for things like translation, queries, OCR, etc. Works with any OpenAI compatible endpoint.

# Dependencies
python3-gi, python3-pil, python3-requests, AppIndicator3.0.1, python3-gi-cairo, gir1.2-gtk-3.0

# Usage
Install Python3 with the relevant dependencies. Download the .py file, make it executable and click to run it.
Go to Settings to make changes to models being used, what language for translations and what API endpoint to use.
The defaults I've configured are what I recommend for good results, including using NanoGPT (www.nano-gpt.com). I've tested it successfully with Ollama and it should work with any OpenAI compatible endpoint.
If you change the defaults, including entering your API key, changes will save to a .json file in ~/.config/llm-assistant. No this isn't particularly secure.

There is a toggle to use a premium text model instead of what you set as the default. I mainly use NanoGPT for my AI API needs, with a subscription that includes significant free use of lots of models. So by default I use those models for each function.
For OCR and image recognition in general, I find GLM and other models more than good enough. But for text, sometimes Deepseek isn't as good at ChatGPT or other more expensive models that aren't included in the subscription. So I've set a toggle to use a
more advanced and thus more expensive model only when needed.

The app has 4 main functions, with hard coded shortcut keys (sorry).
1) Whatever text is in your clipboard will be translated to your selected language.
2) Allows you to select an area of your screen to perform OCR on and translate to your selected language (useful for translating text in images or on parts of websites where you can't select the text.)
3) Let's you ask the text model about whatever text you have in your clipboard, gives some default options or lets you ask your own question.
4) This is a more advanced mode. It lets you select an area of your screen and ask any question about it. It will use your select vision model both to perform OCR and to extract information about the image in general and allow you to ask whatever question about it.

Once you get a response from the AI model, you can then chat with it further if you want to clarify anything.

# Important Notes
I made this for myself, to work on my own device. It is 90% vibe coded, 10% manually tweaked. It should work on any Linux system with a Cinnamon desktop, or any GTK based desktop environment. I've only tested it on Linux Mint Cinnamon 22.2, it may work on other systems, but I've never tested it on anything else. Assume if you use this application it will end in disaster, unless you're willing to manually review the code yourself. I offer no guarantees!
