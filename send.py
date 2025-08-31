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
    "title": "🎶 BLIND MUSIC Update",
    "description": (
        "Hey @everyone! 🚀\n\n"
        "We’ve got an exciting update for you — "
        "**BLIND MUSIC now supports Spotify!** 💚\n\n"

        "✅ **What’s New?**\n"
        "• Play songs directly from **Spotify links** 🎵\n"
        "• Add full **Spotify playlists** to your queue 📜\n"
        "• Smooth integration with YouTube playback 🔗\n\n"

        "⚡ **How to Use**\n"
        "• `!play https://open.spotify.com/track/...`\n"
        "• `!play https://open.spotify.com/playlist/...`\n\n"

        "🎉 Enjoy endless music from both **YouTube & Spotify**!"
    ),
    "color": 5763719,  # Spotify green tone
    "footer": {"text": "BLIND MUSIC • Powered by KHAN_BHAI 🎧"},
    "thumbnail": {
        "url": "https://cdn-icons-png.flaticon.com/512/2111/2111624.png"  # Spotify logo
    }
}



    send_discord_message(webhook, embed=embed_example)
