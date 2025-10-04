# AI-Desktop-Assistant
A simple python tool that allows quick AI lookups of text or screen grabs for things like translation, queries, OCR, etc.

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

The app has 7 functions, with hard coded shortcut keys (sorry).
1) Whatever text is in your clipboard will be translated to your selected language.
2) Whatever text in your clipboard will be explained by the text model (useful if you don't understand something you're reading, error messages, complex jargon, etc.)
3) Will use the OCR model to extract the text from a selected area of your screen and then translate it to your default language using your text model (two steps). Useful when you can't highlight and copy text, such as on some annoying websites, or in images.
4) Explain image. This uses the Vision Model to explain what is in the selected area. Just a single query to the AI to get its direct output.
5) OCR + Explain. This uses the OCR model to extract the text from the selected area, then uses the text model to explain it.
6) Query Image. This is a more advanced function. It uses the OCR model to extract the text from the selection, the Vision Model to describe the image, then allows you to enter text to ask whatever you want of the text model. The OCR text, the image description and your query are all sent to the Text Model to answer.
7) Query Text. Allows you to ask a custom question to the Text Model about whatever text is in your clipboard.

# Important Notes
I made this for myself, to work on my own device. It is 90% vibe coded, 10% manually tweaked. It should work on any Linux system with a Cinnamon desktop. I've only tested it on Linux Mint Cinnamon 22.2, it may work on other systems, but I've never tested it on anything else. Assume if you use this application it will end in disaster, unless you're willing to manually review the code yourself. I offer no guarantees!
