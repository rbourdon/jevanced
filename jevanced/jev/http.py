"""Minimal HTTPS for the Jev client, on CPython and inside Razor Enhanced.

Inside Razor Enhanced (IronPython on .NET Framework) requests go through
.NET's HttpWebRequest, which uses Windows' own TLS and proxy settings.
Elsewhere (tests, tools) the standard library's urllib does the same job.

A transport's ``request`` returns ``(status, text)`` for any HTTP answer,
including errors, and raises JevUnavailableError only when no answer came
back at all. Nothing here logs headers, so the API key never leaves them.
"""

import sys

from jevanced.jev.client import JevUnavailableError


def default_transport():
    if sys.implementation.name == "ironpython":
        return DotNetTransport()
    return UrllibTransport()


class UrllibTransport(object):
    def request(self, method, url, headers, body=None, timeout_s=10.0):
        import socket
        import urllib.error
        import urllib.request

        data = body.encode("utf-8") if body is not None else None
        req = urllib.request.Request(url, data=data, headers=headers, method=method)
        try:
            with urllib.request.urlopen(req, timeout=timeout_s) as resp:
                return resp.status, resp.read().decode("utf-8", "replace")
        except urllib.error.HTTPError as exc:
            return exc.code, exc.read().decode("utf-8", "replace")
        except (urllib.error.URLError, socket.timeout, OSError) as exc:
            raise JevUnavailableError("couldn't reach Jev ({0})".format(_reason(exc)))


def _reason(exc):
    return getattr(exc, "reason", None) or exc.__class__.__name__


class DotNetTransport(object):
    def __init__(self):
        import clr  # noqa: F401  (IronPython only)

        # .NET Framework 4.x may default to old TLS versions. Newer .NET
        # keeps these types elsewhere and already uses modern TLS.
        try:
            from System.Net import SecurityProtocolType, ServicePointManager
            ServicePointManager.SecurityProtocol = (
                ServicePointManager.SecurityProtocol | SecurityProtocolType.Tls12)
        except ImportError:
            pass

    def request(self, method, url, headers, body=None, timeout_s=10.0):
        from System.IO import StreamReader
        from System.Net import WebException, WebRequest
        from System.Text import Encoding

        req = WebRequest.Create(url)
        req.Method = method
        req.Timeout = int(timeout_s * 1000)
        req.ReadWriteTimeout = int(timeout_s * 1000)
        for name, value in headers.items():
            if name.lower() == "content-type":
                req.ContentType = value
            elif name.lower() == "accept":
                req.Accept = value
            else:
                req.Headers.Add(name, value)
        try:
            if body is not None:
                data = Encoding.UTF8.GetBytes(body)
                req.ContentLength = data.Length
                stream = req.GetRequestStream()
                try:
                    stream.Write(data, 0, data.Length)
                finally:
                    stream.Close()
            resp = req.GetResponse()
        except WebException as exc:
            if exc.Response is None:
                raise JevUnavailableError("couldn't reach Jev ({0})".format(exc.Status))
            resp = exc.Response
        try:
            reader = StreamReader(resp.GetResponseStream(), Encoding.UTF8)
            try:
                return int(resp.StatusCode), reader.ReadToEnd()
            finally:
                reader.Close()
        finally:
            resp.Close()
