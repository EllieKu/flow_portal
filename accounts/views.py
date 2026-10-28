from django.contrib.auth.decorators import login_required
from django.shortcuts import render
from django.views.decorators.cache import never_cache

from bots.access import available_bots


@never_cache
@login_required
def home(request):
    return render(request, "bots/list.html", {"bots": available_bots(request.user)})

