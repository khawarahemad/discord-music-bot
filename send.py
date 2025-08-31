import requests
import json

def send_discord_message(webhook_url, content=None, embed=None):
    """
    Sends a message to a Discord channel via webhook.
    
    :param webhook_url: Discord webhook URL (string)
    :param content: Plain text message (string)
    :param embed: Embed message (dict)
    """
    data = {}
    if content:
        data["content"] = content
    if embed:
        data["embeds"] = [embed]  # Discord expects a list of embeds

    headers = {"Content-Type": "application/json"}

    response = requests.post(webhook_url, data=json.dumps(data), headers=headers)

    if response.status_code == 204:
        print("Message sent successfully!")
    else:
        print(f"Failed to send message: {response.status_code}, {response.text}")


if __name__ == "__main__":
    # Replace with your webhook URL
    webhook = "https://discord.com/api/webhooks/1411062415784673351/-Yv5rB1z6r-igZWTpEyXARonOLsmqbDqZZEyELWa5es8mpfKp5vVr-XlCogkAPlk1Yvy"

    # Example embed message
    embed_example = {
    "title": "🎙️ Blind Date Rules & Commands",
    "description": (
        "Welcome to the **Blind Date!** 💞\n"
        "Follow these rules to keep things safe, fair, and fun.\n\n"

        "✅ **How It Works**\n"
        "• Join the **Lobby VC**\n"
        "• Use `/blinddate` to enter the queue\n"
        "• When matched, the bot moves you into a **private voice channel**\n"
        "• Use `/leave` if you want to exit the queue before being matched\n\n"

        "🗣️ **Rules During Your Date**\n"
        "• **Respect & Consent** – Be kind. Stop immediately if asked.\n"
        "• **Voice Only** – No demanding video, selfies, or DMs.\n"
        "• **No Harassment** – No insults, slurs, or offensive behavior.\n"
        "• **Privacy First** – Don’t share or pressure for private info.\n"
        "• **Leave Anytime** – You can disconnect from the VC if uncomfortable.\n\n"

        "🚫 **Strictly Forbidden**\n"
        "• Recording without consent\n"
        "• Spamming commands or abusing the bot\n"
        "• Ignoring moderator instructions\n\n"

        "⚠️ **Safety & Reporting**\n"
        "• Use `/leave` to exit the queue if you change your mind\n"
        "• Report issues via `/report @user` or contact mods directly\n"
        "• Mods may intervene or remove anyone breaking rules\n\n"

        "👉 By using `/blinddate`, you agree to these rules.\n"
        "Have fun, be respectful, and enjoy meeting new people 🎧💬"
    ),
    "color": 15158332,  # A nice warm reddish-pink tone
    "footer": {"text": "Blind Date • Powered by KHAN_BHAI 🚀"},
    "thumbnail": {
        "url": "https://cdn-icons-png.flaticon.com/512/210/210545.png"  # heart icon thumbnail
    }
}


    send_discord_message(webhook, embed=embed_example)
