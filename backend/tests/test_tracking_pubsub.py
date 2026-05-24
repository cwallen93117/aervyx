import asyncio
import threading

from app.services import tracking


def test_task_subscriber_receives_thread_published_message() -> None:
    async def scenario() -> None:
        subscriber = tracking.subscribe(42)
        message = {"event": "position", "id": "pos-1", "task_id": 42}
        try:
            publisher = threading.Thread(target=tracking._publish, args=(42, message))
            publisher.start()

            received = await asyncio.wait_for(subscriber.get(), timeout=1)
            publisher.join(timeout=1)

            assert not publisher.is_alive()
            assert received == message
            assert message["event"] == "position"
        finally:
            tracking.unsubscribe(42, subscriber)

    asyncio.run(scenario())


def test_global_subscriber_receives_thread_published_message() -> None:
    async def scenario() -> None:
        subscriber = tracking.subscribe_global()
        message = {"event": "position", "id": "global-pos-1", "pilot_id": 7}
        try:
            publisher = threading.Thread(target=tracking._publish_global, args=(message,))
            publisher.start()

            received = await asyncio.wait_for(subscriber.get(), timeout=1)
            publisher.join(timeout=1)

            assert not publisher.is_alive()
            assert received == message
            assert message["event"] == "position"
        finally:
            tracking.unsubscribe_global(subscriber)

    asyncio.run(scenario())
