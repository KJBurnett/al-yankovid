# Docker Setup for Al YankoVid

## Unraid / Docker Setup

1.  **Build/Pull**: On Unraid, you'll likely use the `docker-compose.yml` via the terminal or a "Docker Compose" plugin.
    
    ```bash
    docker-compose up -d --build
    ```

2.  **Configuration**:
    -   All data persists in the `./data`, `./archive`, and `./logs` folders mapped relative to where you run the compose file.
    -   **Important**: You must register or link `signal-cli` inside the container before the bot can work.

## Migration (Windows -> Unraid)
To keep your history and user names:
1.  Copy your entire `archive/` folder from Windows to the Unraid `archive/` folder.
2.  Copy `stats.json` and `users_map.json` from Windows into the Unraid `data/` folder.
3.  (Optional) If you have a `signal-cli` data folder, you can copy its contents into `data/` to skip re-linking.

## Linking Existing Signal Account

If you have your primary phone with Signal, you can link the bot as a secondary device:

1.  Start the container. It will loop/fail initially because config is missing.
2.  Run the link command to generate a QR code string:

    ```bash
    docker exec -it al-yankovid signal-cli --config /app/data link -n "AlYankoVid-Bot"
    ```
    
3.  Copy the `tsdevice:/?uuid=...` output string.
4.  Generate a QR code from that text (using a site like `the-qrcode-generator.com`) and scan it with your phone's Signal app ("Linked Devices").
5.  Restart the container: `docker restart al-yankovid`

## Registering a New Number

If using a dedicated SIM/number for the bot:

1.  Register (you will get an SMS):
    ```bash
    docker exec -it al-yankovid signal-cli --config /app/data -u +15551234567 register
    ```
    
2.  Verify with code:
    ```bash
    docker exec -it al-yankovid signal-cli --config /app/data -u +15551234567 verify 123456
    ```
    
3.  Restart container.
