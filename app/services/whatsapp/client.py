"""WhatsApp Cloud API client service.

Wraps Meta's WhatsApp Cloud API for sending text, interactive,
image, template, and location-request messages.
"""

from typing import Any

import httpx

from app.core.config import settings


class WhatsAppClient:
    """WhatsApp Cloud API client for sending messages."""

    def __init__(self) -> None:
        """Initialize the WhatsApp client."""
        self.base_url = f"https://graph.facebook.com/{settings.WHATSAPP_API_VERSION}"
        self.client = httpx.AsyncClient(
            headers={"Authorization": f"Bearer {settings.WHATSAPP_TOKEN}"},
            timeout=30.0,
        )

    async def close(self) -> None:
        """Close the HTTP client."""
        await self.client.aclose()

    def _get_messages_url(self) -> str:
        """Get the messages endpoint URL."""
        return f"{self.base_url}/{settings.WHATSAPP_PHONE_NUMBER_ID}/messages"

    async def send_text(self, to: str, message: str) -> dict[str, Any]:
        """Send a text message.

        Args:
            to: Recipient phone number in international format.
            message: Text message to send.

        Returns:
            API response as dictionary.
        """
        url = self._get_messages_url()
        payload = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": to,
            "type": "text",
            "text": {"preview_url": False, "body": message},
        }
        response = await self.client.post(url, json=payload)
        response.raise_for_status()
        return response.json()

    async def send_buttons(
        self,
        to: str,
        body: str,
        buttons: list[dict[str, Any]],
        header: str | None = None,
        footer: str | None = None,
    ) -> dict[str, Any]:
        """Send an interactive button message.

        Args:
            to: Recipient phone number.
            body: Message body text.
            buttons: List of button configurations.
            header: Optional header text.
            footer: Optional footer text.

        Returns:
            API response as dictionary.
        """
        url = self._get_messages_url()
        interactive: dict[str, Any] = {
            "type": "button",
            "body": {"text": body},
            "action": {"buttons": buttons},
        }

        if header:
            interactive["header"] = {"type": "text", "text": header}

        if footer:
            interactive["footer"] = {"text": footer}

        payload = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": to,
            "type": "interactive",
            "interactive": interactive,
        }
        response = await self.client.post(url, json=payload)
        response.raise_for_status()
        return response.json()

    async def send_list(
        self,
        to: str,
        body: str,
        button_text: str,
        sections: list[dict[str, Any]],
        header: str | None = None,
        footer: str | None = None,
    ) -> dict[str, Any]:
        """Send an interactive list message.

        Args:
            to: Recipient phone number.
            body: Message body text.
            button_text: Text for the list button.
            sections: List sections with rows.
            header: Optional header text.
            footer: Optional footer text.

        Returns:
            API response as dictionary.
        """
        url = self._get_messages_url()
        interactive: dict[str, Any] = {
            "type": "list",
            "body": {"text": body},
            "action": {"button": button_text, "sections": sections},
        }

        if header:
            interactive["header"] = {"type": "text", "text": header}

        if footer:
            interactive["footer"] = {"text": footer}

        payload = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": to,
            "type": "interactive",
            "interactive": interactive,
        }
        response = await self.client.post(url, json=payload)
        response.raise_for_status()
        return response.json()

    async def request_location(self, to: str, body: str) -> dict[str, Any]:
        """Request the user's location.

        Args:
            to: Recipient phone number.
            body: Message body text explaining why location is needed.

        Returns:
            API response as dictionary.
        """
        url = self._get_messages_url()
        payload = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": to,
            "type": "interactive",
            "interactive": {
                "type": "location_request_message",
                "body": {"text": body},
                "action": {"name": "send_location"},
            },
        }
        response = await self.client.post(url, json=payload)
        response.raise_for_status()
        return response.json()

    async def send_image(
        self,
        to: str,
        image_url: str,
        caption: str | None = None,
    ) -> dict[str, Any]:
        """Send an image message.

        Args:
            to: Recipient phone number.
            image_url: URL of the image to send.
            caption: Optional image caption.

        Returns:
            API response as dictionary.
        """
        url = self._get_messages_url()
        image_data: dict[str, Any] = {"link": image_url}
        if caption:
            image_data["caption"] = caption

        payload = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": to,
            "type": "image",
            "image": image_data,
        }
        response = await self.client.post(url, json=payload)
        response.raise_for_status()
        return response.json()

    async def get_media_url(self, media_id: str) -> str:
        """Get the download URL for a media file.

        Args:
            media_id: WhatsApp media ID.

        Returns:
            URL to download the media file.
        """
        url = f"{self.base_url}/{media_id}"
        response = await self.client.get(url)
        response.raise_for_status()
        data = response.json()
        return data["url"]

    async def download_media(self, media_id: str) -> bytes:
        """Download a media file from WhatsApp.

        Args:
            media_id: WhatsApp media ID.

        Returns:
            Media file content as bytes.
        """
        media_url = await self.get_media_url(media_id)
        response = await self.client.get(media_url)
        response.raise_for_status()
        return response.content

    async def mark_as_read(self, message_id: str) -> dict[str, Any]:
        """Mark a message as read.

        Args:
            message_id: WhatsApp message ID to mark as read.

        Returns:
            API response as dictionary.
        """
        url = self._get_messages_url()
        payload = {
            "messaging_product": "whatsapp",
            "status": "read",
            "message_id": message_id,
        }
        response = await self.client.post(url, json=payload)
        response.raise_for_status()
        return response.json()

    async def send_template(
        self,
        to: str,
        template_name: str,
        language_code: str = "en",
        components: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        """Send a template message.

        Args:
            to: Recipient phone number.
            template_name: Name of the approved template.
            language_code: Language code for the template.
            components: Optional template components with variables.

        Returns:
            API response as dictionary.
        """
        url = self._get_messages_url()
        template: dict[str, Any] = {
            "name": template_name,
            "language": {"code": language_code},
        }

        if components:
            template["components"] = components

        payload = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": to,
            "type": "template",
            "template": template,
        }
        response = await self.client.post(url, json=payload)
        response.raise_for_status()
        return response.json()
