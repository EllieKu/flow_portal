from unittest.mock import patch

from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase


class BotKeyMigrationTests(TransactionTestCase):
    previous = ("bots", "0001_initial")
    current = ("bots", "0002_remove_bot_api_key_env_bot_api_key")

    def test_environment_keys_are_preserved_and_missing_keys_remain_empty(self):
        executor = MigrationExecutor(connection)
        executor.migrate([self.previous])
        try:
            old_apps = executor.loader.project_state([self.previous]).apps
            OldBot = old_apps.get_model("bots", "Bot")
            old = OldBot.objects.create(name="Configured", api_key_env="DIFY_MIGRATION_TEST_KEY")
            missing = OldBot.objects.create(name="Missing", api_key_env="DIFY_MIGRATION_MISSING_KEY")
            with patch.dict("os.environ", {
                "DIFY_MIGRATION_TEST_KEY": "app-migration-secret",
                "DIFY_MIGRATION_MISSING_KEY": "",
            }):
                executor = MigrationExecutor(connection)
                executor.migrate([self.current])
            apps = executor.loader.project_state([self.current]).apps
            Bot = apps.get_model("bots", "Bot")
            self.assertEqual(Bot.objects.get(pk=old.pk).api_key, "app-migration-secret")
            self.assertEqual(Bot.objects.get(pk=missing.pk).api_key, "")
        finally:
            MigrationExecutor(connection).migrate([self.current])
