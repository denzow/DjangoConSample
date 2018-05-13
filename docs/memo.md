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



django.db.migrations.operations.special.RunPython
self.code(from_state.apps, schema_editor)

```python
>>> from django.apps import apps
>>> apps
<django.apps.registry.Apps object at 0x10679ada0>
>>> apps.get_model('app1', 'Book')
<class 'app1.models.Book'>
>>> apps.get_model('app1', 'Author')
<class 'app1.models.Author'>
```

-> これはFakeではない

django.apps.registry.Apps#get_model

django.db.migrations.state.AppConfigStub