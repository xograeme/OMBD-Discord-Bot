import asyncio
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

import discord

from bot import (
    WatchlistPaginationView,
    build_watchlist_embed,
    fetch_watchlist_records,
    server_group,
    watchlist_watched,
)


class TestWatchlistPagination(unittest.TestCase):
    """Unit tests for watchlist pagination, in-card actions, and view behavior."""

    def setUp(self):
        self.sample_items = [
            {"id": i, "title": f"Movie {i}", "added_by": 1000 + i}
            for i in range(1, 13)
        ]

    def test_page_slicing_math(self):
        """Test page calculation and item slicing across different counts."""
        # 0 items
        embed_empty = build_watchlist_embed([], page=0, page_size=5, is_server=True)
        self.assertIn("The server watchlist is currently empty", embed_empty.description)

        # 1-5 items (1 page)
        items_5 = self.sample_items[:5]
        embed_5 = build_watchlist_embed(items_5, page=0, page_size=5, is_server=True)
        self.assertIn("Page 1 of 1", embed_5.footer.text)
        self.assertIn("5 movies total", embed_5.footer.text)
        self.assertIn("**1.** Movie 1", embed_5.description)
        self.assertIn("**5.** Movie 5", embed_5.description)

        # 6 items (2 pages)
        items_6 = self.sample_items[:6]
        view_6 = WatchlistPaginationView(
            author_id=123,
            guild_id=456,
            user_id=None,
            is_server=True,
            items=items_6,
            page_size=5
        )
        self.assertEqual(view_6.total_pages, 2)

        # 12 items (3 pages)
        view_12 = WatchlistPaginationView(
            author_id=123,
            guild_id=456,
            user_id=None,
            is_server=True,
            items=self.sample_items,
            page_size=5
        )
        self.assertEqual(view_12.total_pages, 3)

        # Check page 1 (second page, 0-indexed page=1) slicing
        embed_page1 = build_watchlist_embed(self.sample_items, page=1, page_size=5, is_server=True)
        self.assertIn("Page 2 of 3", embed_page1.footer.text)
        self.assertIn("**6.** Movie 6", embed_page1.description)
        self.assertIn("**10.** Movie 10", embed_page1.description)

        # Check page 2 (third page, 0-indexed page=2) slicing
        embed_page2 = build_watchlist_embed(self.sample_items, page=2, page_size=5, is_server=True)
        self.assertIn("Page 3 of 3", embed_page2.footer.text)
        self.assertIn("**11.** Movie 11", embed_page2.description)
        self.assertIn("**12.** Movie 12", embed_page2.description)

    def test_boundary_navigation_buttons(self):
        """Test Previous/Next button enable/disable states at boundaries."""
        # Multi-page on first page (page 0)
        view_first = WatchlistPaginationView(
            author_id=123,
            guild_id=456,
            user_id=None,
            is_server=True,
            items=self.sample_items,
            page=0,
            page_size=5
        )
        prev_btn = next(c for c in view_first.children if getattr(c, "custom_id", None) == "watchlist_btn_prev")
        next_btn = next(c for c in view_first.children if getattr(c, "custom_id", None) == "watchlist_btn_next")
        self.assertTrue(prev_btn.disabled)
        self.assertFalse(next_btn.disabled)

        # Multi-page on last page (page 2)
        view_last = WatchlistPaginationView(
            author_id=123,
            guild_id=456,
            user_id=None,
            is_server=True,
            items=self.sample_items,
            page=2,
            page_size=5
        )
        prev_btn_l = next(c for c in view_last.children if getattr(c, "custom_id", None) == "watchlist_btn_prev")
        next_btn_l = next(c for c in view_last.children if getattr(c, "custom_id", None) == "watchlist_btn_next")
        self.assertFalse(prev_btn_l.disabled)
        self.assertTrue(next_btn_l.disabled)

        # Single page (3 items)
        view_single = WatchlistPaginationView(
            author_id=123,
            guild_id=456,
            user_id=None,
            is_server=True,
            items=self.sample_items[:3],
            page=0,
            page_size=5
        )
        prev_btn_s = next(c for c in view_single.children if getattr(c, "custom_id", None) == "watchlist_btn_prev")
        next_btn_s = next(c for c in view_single.children if getattr(c, "custom_id", None) == "watchlist_btn_next")
        self.assertTrue(prev_btn_s.disabled)
        self.assertTrue(next_btn_s.disabled)

    def test_clamping_after_removal(self):
        """Test that current_page clamps safely when items are removed."""
        # 6 items: page 0 has 5, page 1 has 1 item
        items_6 = self.sample_items[:6]
        view = WatchlistPaginationView(
            author_id=123,
            guild_id=456,
            user_id=None,
            is_server=True,
            items=items_6,
            page=1,
            page_size=5
        )
        self.assertEqual(view.current_page, 1)
        self.assertEqual(view.total_pages, 2)

        # Remove the item on page 1, leaving 5 items (total_pages drops to 1)
        view.items = items_6[:5]
        view._clamp_page()
        self.assertEqual(view.current_page, 0)
        self.assertEqual(view.total_pages, 1)

    def test_empty_watchlist_embed_and_components(self):
        """Test clean empty embeds and empty view component state."""
        # Server empty embed
        server_embed = build_watchlist_embed([], 0, 5, is_server=True)
        self.assertEqual(server_embed.title, "🍿 Server Watchlist")
        self.assertIn("The server watchlist is currently empty", server_embed.description)

        # Personal empty embed
        personal_embed = build_watchlist_embed([], 0, 5, is_server=False, user_name="Tester")
        self.assertEqual(personal_embed.title, "🍿 Tester's Watchlist")
        self.assertIn("Your personal watchlist is empty!", personal_embed.description)

        # Empty view should clear all select and button components
        empty_view = WatchlistPaginationView(
            author_id=123,
            guild_id=456,
            user_id=None,
            is_server=True,
            items=[],
            page_size=5
        )
        self.assertEqual(len(empty_view.children), 0)

    def test_interaction_check_permission(self):
        """Test that only the invoking author can use the view controls."""
        view = WatchlistPaginationView(
            author_id=999,
            guild_id=456,
            user_id=None,
            is_server=True,
            items=self.sample_items[:3]
        )

        # Author interaction
        interaction_author = MagicMock()
        interaction_author.user.id = 999
        res_author = asyncio.run(view.interaction_check(interaction_author))
        self.assertTrue(res_author)

        # Unauthorized user interaction
        interaction_other = MagicMock()
        interaction_other.user.id = 888
        interaction_other.response.send_message = AsyncMock()
        res_other = asyncio.run(view.interaction_check(interaction_other))
        self.assertFalse(res_other)
        interaction_other.response.send_message.assert_called_once()
        self.assertIn("Only the person who requested", interaction_other.response.send_message.call_args[0][0])

    def test_timeout_disables_components(self):
        """Test that view on_timeout disables all children and edits message."""
        view = WatchlistPaginationView(
            author_id=123,
            guild_id=456,
            user_id=None,
            is_server=True,
            items=self.sample_items[:5]
        )
        mock_msg = MagicMock()
        mock_msg.edit = AsyncMock()
        view.message = mock_msg

        self.assertFalse(all(c.disabled for c in view.children))
        asyncio.run(view.on_timeout())
        self.assertTrue(all(c.disabled for c in view.children))
        mock_msg.edit.assert_called_once_with(view=view)

    def test_watched_callback_server(self):
        """Test watched select callback moves item to server_history and updates view."""
        view = WatchlistPaginationView(
            author_id=123,
            guild_id=456,
            user_id=None,
            is_server=True,
            items=[{"id": 10, "title": "Inception", "added_by": 123}],
            page_size=5
        )
        interaction = MagicMock()
        interaction.response.defer = AsyncMock()
        interaction.response.is_done.return_value = True
        interaction.edit_original_response = AsyncMock()
        interaction.data = {"values": ["10"]}
        interaction.user.id = 123

        with patch("bot.async_db_query", new_callable=AsyncMock) as mock_query, \
             patch("bot.fetch_watchlist_records", new_callable=AsyncMock) as mock_fetch:
            mock_query.side_effect = [("Inception",), None, None]
            mock_fetch.return_value = []
            asyncio.run(view._watched_callback(interaction))

            # Verify SELECT, DELETE, and INSERT into server_history
            self.assertEqual(mock_query.call_count, 3)
            select_call_sql = mock_query.call_args_list[0][0][0]
            self.assertIn("SELECT movie_title FROM server_watchlist", select_call_sql)
            delete_call_sql = mock_query.call_args_list[1][0][0]
            self.assertIn("DELETE FROM server_watchlist", delete_call_sql)
            insert_call_sql = mock_query.call_args_list[2][0][0]
            self.assertIn("INSERT INTO server_history", insert_call_sql)

            # View should now be empty and updated
            self.assertEqual(len(view.items), 0)
            interaction.edit_original_response.assert_called_once()

    def test_remove_callback_personal(self):
        """Test remove callback deletes from personal_watchlist."""
        view = WatchlistPaginationView(
            author_id=123,
            guild_id=None,
            user_id=123,
            is_server=False,
            items=[{"id": 20, "title": "Interstellar", "added_by": None}],
            page_size=5
        )
        interaction = MagicMock()
        interaction.response.defer = AsyncMock()
        interaction.response.is_done.return_value = True
        interaction.edit_original_response = AsyncMock()
        interaction.data = {"values": ["20"]}
        interaction.user.id = 123

        with patch("bot.async_db_query", new_callable=AsyncMock) as mock_query, \
             patch("bot.fetch_watchlist_records", new_callable=AsyncMock) as mock_fetch:
            mock_fetch.return_value = []
            asyncio.run(view._remove_callback(interaction))

            mock_query.assert_called_once()
            sql = mock_query.call_args[0][0]
            self.assertIn("DELETE FROM personal_watchlist", sql)

    def test_watchlist_watched_command_unchanged(self):
        """Test that the existing /watchlist watched command remains defined and unchanged."""
        watched_cmd = next((c for c in server_group.commands if c.name == "watched"), None)
        self.assertIsNotNone(watched_cmd, "/watchlist watched command should still exist on server_group")
        self.assertEqual(watched_cmd, watchlist_watched)
        self.assertIn("title", [p.name for p in watched_cmd.parameters])


if __name__ == "__main__":
    unittest.main()
