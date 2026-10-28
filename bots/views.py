from django.contrib.auth.decorators import login_required
from django.shortcuts import render
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET

from .access import authorized_bot, available_bots


@never_cache
@login_required
@require_GET
def bot_list(request):
    return render(request, "bots/list.html", {"bots": available_bots(request.user)})


@never_cache
@login_required
@require_GET
def bot_chat(request, pk):
    bot = authorized_bot(request.user, pk)
    return render(request, "bots/chat.html", {"bot": bot})

