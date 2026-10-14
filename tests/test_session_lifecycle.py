import asyncio
import inspect
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

import aiohttp

import bot
from bot import MovieBot, fetch_omdb_data, fetch_omdb_search
import jev_client
from jev_client import JevClient
import tmdb_client


class TestSessionLifecycle(unittest.TestCase):
    """Test MovieBot session creation, configuration, and shutdown lifecycle."""

    def test_setup_hook_creates_configured_session_and_jev(self):
        """Assert setup_hook creates self.session with expected timeout and connector, and wires JevClient."""
        bot_instance = MovieBot()
        self.assertIsNone(bot_instance.session)
        self.assertIsNone(bot_instance.jev)

        with patch.object(bot_instance.tree, "sync", new_callable=AsyncMock) as mock_sync:
            try:
                asyncio.run(bot_instance.setup_hook())

                mock_sync.assert_called_once()
                self.assertIsNotNone(bot_instance.session)
                self.assertIsInstance(bot_instance.session, aiohttp.ClientSession)
                self.assertFalse(bot_instance.session.closed)

                # Check timeout configuration
                timeout = bot_instance.session.timeout
                self.assertEqual(timeout.total, 15)
                self.assertEqual(timeout.connect, 5)

                # Check connector configuration
                connector = bot_instance.session.connector
                self.assertEqual(connector.limit, 100)
                self.assertEqual(connector.limit_per_host, 20)
                self.assertEqual(connector._cached_hosts._ttl, 300)

                # Check JevClient wired with shared session
                self.assertIsNotNone(bot_instance.jev)
                self.assertIsInstance(bot_instance.jev, JevClient)
                self.assertIs(bot_instance.jev.session, bot_instance.session)
            finally:
                if bot_instance.session and not bot_instance.session.closed:
                    asyncio.run(bot_instance.session.close())

    def test_close_cleanly_closes_session(self):
        """Assert MovieBot.close closes self.session and super().close()."""
        bot_instance = MovieBot()
        mock_session = MagicMock()
        mock_session.closed = False
        mock_session.close = AsyncMock()
        bot_instance.session = mock_session

        with patch("discord.Client.close", new_callable=AsyncMock) as mock_super_close:
            asyncio.run(bot_instance.close())
            mock_session.close.assert_called_once()
            mock_super_close.assert_called_once()

    def test_close_guards_against_none_or_closed_session(self):
        """Assert MovieBot.close handles None or already-closed session without error."""
        # Case 1: session is None
        bot_instance = MovieBot()
        bot_instance.session = None
        with patch("discord.Client.close", new_callable=AsyncMock) as mock_super_close:
            asyncio.run(bot_instance.close())
            mock_super_close.assert_called_once()

        # Case 2: session is already closed
        bot_instance2 = MovieBot()
        mock_closed_session = MagicMock()
        mock_closed_session.closed = True
        mock_closed_session.close = AsyncMock()
        bot_instance2.session = mock_closed_session
        with patch("discord.Client.close", new_callable=AsyncMock) as mock_super_close2:
            asyncio.run(bot_instance2.close())
            mock_closed_session.close.assert_not_called()
            mock_super_close2.assert_called_once()


class TestClientsUseSharedSession(unittest.TestCase):
    """Test that clients make requests through the provided session and honor timeouts."""

    def test_fetch_omdb_data_uses_passed_session(self):
        """Assert fetch_omdb_data executes request via passed session with timeout override."""
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.json = AsyncMock(return_value={"Title": "Inception", "Response": "True"})

        mock_cm = AsyncMock()
        mock_cm.__aenter__.return_value = mock_response

        mock_session = MagicMock()
        mock_session.get.return_value = mock_cm

        res = asyncio.run(fetch_omdb_data(mock_session, "Inception", 2010))

        self.assertEqual(res.get("Title"), "Inception")
        mock_session.get.assert_called_once()
        args, kwargs = mock_session.get.call_args
        self.assertEqual(args[0], "https://www.omdbapi.com/")
        self.assertEqual(kwargs["params"]["t"], "Inception")
        self.assertEqual(kwargs["params"]["y"], "2010")
        self.assertIsInstance(kwargs["timeout"], aiohttp.ClientTimeout)
        self.assertEqual(kwargs["timeout"].total, 15)

    def test_fetch_omdb_search_uses_passed_session(self):
        """Assert fetch_omdb_search executes requests via passed session."""
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.json = AsyncMock(return_value={
            "Response": "True",
            "Search": [{"Title": "Star Wars", "imdbID": "tt0076759"}]
        })

        mock_cm = AsyncMock()
        mock_cm.__aenter__.return_value = mock_response

        mock_session = MagicMock()
        mock_session.get.return_value = mock_cm

        res = asyncio.run(fetch_omdb_search(mock_session, "Star Wars", max_pages=1))

        self.assertEqual(len(res), 1)
        self.assertEqual(res[0]["Title"], "Star Wars")
        mock_session.get.assert_called_once()
        args, kwargs = mock_session.get.call_args
        self.assertEqual(kwargs["params"]["s"], "Star Wars")
        self.assertIsInstance(kwargs["timeout"], aiohttp.ClientTimeout)
        self.assertEqual(kwargs["timeout"].total, 15)

    def test_tmdb_fetch_person_id_uses_passed_session(self):
        """Assert fetch_tmdb_person_id uses passed session with 5s timeout."""
        with patch.object(tmdb_client, "TMDB_ACCESS_TOKEN", "fake_token"):
            mock_response = MagicMock()
            mock_response.status = 200
            mock_response.json = AsyncMock(return_value={"results": [{"id": 1234}]})

            mock_cm = AsyncMock()
            mock_cm.__aenter__.return_value = mock_response

            mock_session = MagicMock()
            mock_session.get.return_value = mock_cm

            res = asyncio.run(tmdb_client.fetch_tmdb_person_id(mock_session, "Christopher Nolan"))
            self.assertEqual(res, 1234)
            mock_session.get.assert_called_once()
            _, kwargs = mock_session.get.call_args
            self.assertEqual(kwargs.get("timeout"), 5)

    def test_tmdb_fetch_tv_id_uses_passed_session(self):
        """Assert fetch_tmdb_tv_id uses passed session with 5s timeout."""
        with patch.object(tmdb_client, "TMDB_ACCESS_TOKEN", "fake_token"):
            mock_response = MagicMock()
            mock_response.status = 200
            mock_response.json = AsyncMock(return_value={"tv_results": [{"id": 5678}]})

            mock_cm = AsyncMock()
            mock_cm.__aenter__.return_value = mock_response

            mock_session = MagicMock()
            mock_session.get.return_value = mock_cm

            res = asyncio.run(tmdb_client.fetch_tmdb_tv_id(mock_session, "tt0944947"))
            self.assertEqual(res, 5678)
            mock_session.get.assert_called_once()
            _, kwargs = mock_session.get.call_args
            self.assertEqual(kwargs.get("timeout"), 5)

    def test_tmdb_discover_movies_uses_passed_session(self):
        """Assert discover_movies uses passed session with 10s timeout and forwards to fetch_tmdb_person_id."""
        with patch.object(tmdb_client, "TMDB_ACCESS_TOKEN", "fake_token"), \
             patch("tmdb_client.fetch_tmdb_person_id", new_callable=AsyncMock) as mock_person_id:
            mock_person_id.return_value = 9999

            mock_response = MagicMock()
            mock_response.status = 200
            mock_response.json = AsyncMock(return_value={"results": [{"title": "Tenet"}]})

            mock_cm = AsyncMock()
            mock_cm.__aenter__.return_value = mock_response

            mock_session = MagicMock()
            mock_session.get.return_value = mock_cm

            res = asyncio.run(tmdb_client.discover_movies(mock_session, genre="action", person_name="Nolan"))
            self.assertEqual(len(res), 1)
            self.assertEqual(res[0]["title"], "Tenet")

            # Check that fetch_tmdb_person_id was called with the session
            mock_person_id.assert_called_once_with(mock_session, "Nolan")

            # Check discover_movies GET request
            mock_session.get.assert_called_once()
            _, kwargs = mock_session.get.call_args
            self.assertEqual(kwargs.get("timeout"), 10)

    def test_jev_client_uses_passed_session(self):
        """Assert JevClient stores passed session, never closes it, and uses it with timeout override."""
        mock_response = MagicMock()
        mock_response.status = 200
        mock_response.json = AsyncMock(return_value={
            "answers": {"intent": {"choice": "search"}}
        })

        mock_cm = AsyncMock()
        mock_cm.__aenter__.return_value = mock_response

        mock_session = MagicMock()
        mock_session.post.return_value = mock_cm

        client = JevClient(mock_session, timeout=12.0)
        self.assertIs(client.session, mock_session)

        with patch.object(client, "api_key", "test_key"):
            answers = asyncio.run(client.decide("state", {"q": {}}))
            self.assertEqual(answers, {"intent": {"choice": "search"}})

            mock_session.post.assert_called_once()
            _, kwargs = mock_session.post.call_args
            self.assertEqual(kwargs.get("timeout").total, 12.0)

            # Ensure JevClient never called session.close()
            mock_session.close.assert_not_called()


class TestNoClientConstructsOwnSession(unittest.TestCase):
    """Assert that none of the client modules/functions construct their own ClientSession."""

    def test_source_code_has_no_clientsession_calls(self):
        """Verify that ClientSession is not instantiated in tmdb_client.py, jev_client.py, or outside setup_hook in bot.py."""
        # 1. tmdb_client.py
        tmdb_src = inspect.getsource(tmdb_client)
        self.assertNotIn("ClientSession(", tmdb_src)

        # 2. jev_client.py
        jev_src = inspect.getsource(jev_client)
        self.assertNotIn("ClientSession(", jev_src)

        # 3. bot.py functions: fetch_omdb_data, fetch_omdb_search
        omdb_data_src = inspect.getsource(fetch_omdb_data)
        self.assertNotIn("ClientSession(", omdb_data_src)

        omdb_search_src = inspect.getsource(fetch_omdb_search)
        self.assertNotIn("ClientSession(", omdb_search_src)

        # 4. In bot.py as a whole, ClientSession( must only appear once, in setup_hook
        with open("bot.py", "r", encoding="utf-8") as f:
            bot_lines = f.readlines()
        session_hits = [i for i, line in enumerate(bot_lines, 1) if "ClientSession(" in line]
        self.assertEqual(len(session_hits), 1)

        setup_hook_src = inspect.getsource(MovieBot.setup_hook)
        self.assertIn("ClientSession(", setup_hook_src)


if __name__ == "__main__":
    unittest.main()
