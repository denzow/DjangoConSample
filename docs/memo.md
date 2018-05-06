Django migration挙動メモ
===============================

command
---------------


django.core.management.ManagementUtility#execute


            self.fetch_command(subcommand).run_from_argv(self.argv)


django.core.management.get_commands
-> 全部のコマンドを列挙する

django.core.management.ManagementUtility#fetch_command
-> get_commandsから対応するコマンドを呼び出して実行する

