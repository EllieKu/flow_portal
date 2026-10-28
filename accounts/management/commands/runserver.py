from django.contrib.staticfiles.management.commands.runserver import Command as StaticFilesRunserver


class Command(StaticFilesRunserver):
    default_port = "8002"
