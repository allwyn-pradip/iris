from falcon import HTTPBadRequest

from iris.webhooks.webhook import webhook


class freshservice(webhook):
    def validate_post(self, body):
        if not all(k in body for k in ("title", "description", "tags", "ticket_id")):
            raise HTTPBadRequest('missing event_id and/or details attributes')

    def on_post(self, req, resp):
        '''
        This endpoint is compatible with the webhook posts from FreshService.
        Configure a FreshService notification to post to a URL with the following
        parameters

        "http://iris:16649/v0/webhooks/freshservice?application=test-app&key=abc&plan=teamA"

        Where application points to an application and key in Iris.

        For every POST from FreshService, a new incident will be created, if the plan label
        is attached to an alert.
        '''
        plan = req.get_param('plan', required=False)
        if plan is None:
            raise HTTPBadRequest('missing plan in freshservice webhook url parameters')

        super().on_post(req, resp, plan)
