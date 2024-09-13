# YouTube Video Data to Google Sheets

This repository allows you to seamlessly save YouTube video data into Google Sheets.

## Features

- **Video Links**: Provide a video link, and the data will be saved to the corresponding video page.
- **Channel Links**: Provide a channel link, and the data will be saved to the channel's page.

To simplify usage, I've included a `run.bat` file. However, there are a few setup steps you'll need to complete:

## Setup Instructions

1. **Obtain Credentials**: Get a `credentials.json` file with YouTube API credentials from the Google Cloud Console.
2. **Share Your Google Sheet**: Share your Google Sheet with the `client_email` found inside the `credentials.json` file.

## How to Use

- **Copy Credentials**: Place the `credentials.json` file into the project directory.
- **Run the Application**: Execute `run.bat`.
- **Configure APIs**: In the web interface, go to the **Settings** section and input your API keys.
- **Start Saving**: Begin adding your links, and watch as the data populates your Google Sheet!

---

NOTE

I developed this project entirely using ChatGPT's *4o model. Without any coding knowledge,
i simply communicated my requests to the 4o model and shared any errors i encountered via copy-paste.
If you have any questions, i might not be able to solve them myself, but i almost certain that GPT can help me.

  *ChatGPT 4o – July 2024
