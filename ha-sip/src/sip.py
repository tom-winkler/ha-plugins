import ipaddress
import socket
from typing import Optional

import pjsua2 as pj

from options_global import GlobalOptions
from log import log


class MyEndpointConfig(object):
    def __init__(self, port: int, log_level: int, name_server: list[str], global_options: GlobalOptions):
        self.port = port
        self.log_level = log_level
        self.name_server = name_server
        self.global_options = global_options


def _is_local_ip(ip: str) -> bool:
    try:
        addr = ipaddress.ip_address(ip)
    except ValueError:
        return False
    family = socket.AF_INET6 if addr.version == 6 else socket.AF_INET
    sock = socket.socket(family, socket.SOCK_DGRAM)
    try:
        sock.bind((ip, 0))
        return True
    except OSError:
        return False
    finally:
        sock.close()


def _validate_bind_ip(bind_ip: str) -> None:
    if not _is_local_ip(bind_ip):
        raise RuntimeError(
            f"bind_ip '{bind_ip}' is not a valid local address on this host (or cannot be bound). "
            "Fix the configuration or remove --bind-ip to use the default selection."
        )


def _validate_media_ip(media_ip: str) -> bool:
    if not _is_local_ip(media_ip):
        log(None, f"Warning: media_ip '{media_ip}' is not a valid local address on this host. Falling back to default behaviour.")
        return False
    return True


def _apply_transport_ip_config(tp_cfg: pj.TransportConfig, bind_ip: Optional[str], public_ip: Optional[str]) -> None:
    if bind_ip:
        if hasattr(tp_cfg, 'boundAddress'):
            tp_cfg.boundAddress = bind_ip
        else:
            log(None, 'Warning: pjsua2 TransportConfig.boundAddress not available; cannot force bind-ip for SIP transport.')
    if public_ip:
        if hasattr(tp_cfg, 'publicAddress'):
            tp_cfg.publicAddress = public_ip
        else:
            log(None, 'Warning: pjsua2 TransportConfig.publicAddress not available; cannot force advertised IP for SIP transport.')


def _apply_media_config(ep_cfg: pj.EpConfig, bind_ip: Optional[str], media_ip: Optional[str], rtp_port_min: Optional[int], rtp_port_max: Optional[int]) -> None:
    if not hasattr(ep_cfg, 'medConfig'):
        return
    med_cfg = ep_cfg.medConfig

    if bind_ip:
        if hasattr(med_cfg, 'boundAddress'):
            med_cfg.boundAddress = bind_ip
        else:
            log(None, 'Warning: pjsua2 MedConfig.boundAddress not available; cannot force bind-ip for RTP/media sockets.')
    if media_ip:
        if hasattr(med_cfg, 'publicAddress'):
            med_cfg.publicAddress = media_ip
        else:
            log(None, 'Warning: pjsua2 MedConfig.publicAddress not available; cannot force media-ip in SDP.')

    if rtp_port_min is None and rtp_port_max is None:
        return

    if rtp_port_min is not None and rtp_port_max is not None and rtp_port_max < rtp_port_min:
        log(None, f'Warning: rtp-port-max ({rtp_port_max}) is less than rtp-port-min ({rtp_port_min}); ignoring RTP port range override.')
        return

    if rtp_port_min is not None:
        if hasattr(med_cfg, 'rtpPort'):
            med_cfg.rtpPort = rtp_port_min
        else:
            log(None, 'Warning: pjsua2 MedConfig.rtpPort not available; cannot force RTP port minimum.')

    if rtp_port_min is not None and rtp_port_max is not None:
        if hasattr(med_cfg, 'rtpPortRange'):
            med_cfg.rtpPortRange = (rtp_port_max - rtp_port_min) + 1
        else:
            log(None, 'Warning: pjsua2 MedConfig.rtpPortRange not available; cannot force RTP port range.')


def create_endpoint(ep_config: MyEndpointConfig) -> pj.Endpoint:
    ep_cfg = pj.EpConfig()
    ep_cfg.logConfig.level = ep_config.log_level
    ep_cfg.uaConfig.threadCnt = 0
    ep_cfg.uaConfig.mainThreadOnly = True
    if ep_config.name_server:
        nameserver = pj.StringVector()
        for ns in ep_config.name_server:
            nameserver.append(ns)
        ep_cfg.uaConfig.nameserver = nameserver
    if ep_config.global_options.stun_server:
        log(None, "STUN server enabled: %s" % ep_config.global_options.stun_server)
        ep_cfg.uaConfig.stunServer.append(ep_config.global_options.stun_server)

    bind_ip = ep_config.global_options.bind_ip
    media_ip = ep_config.global_options.media_ip
    if bind_ip:
        log(None, f"Binding SIP signalling to IP: {bind_ip}")
        _validate_bind_ip(bind_ip)
    if media_ip and not _validate_media_ip(media_ip):
        media_ip = None

    # Apply endpoint-level media configuration (best-effort; depends on available pjsua2 bindings).
    _apply_media_config(
        ep_cfg,
        bind_ip=bind_ip,
        media_ip=media_ip,
        rtp_port_min=ep_config.global_options.rtp_port_min,
        rtp_port_max=ep_config.global_options.rtp_port_max,
    )

    end_point = pj.Endpoint()
    end_point.libCreate()
    end_point.libInit(ep_cfg)
    codecs = end_point.codecEnum2()
    log(None, "Supported audio codecs: %s" % ", ".join(c.codecId for c in codecs))
    end_point.audDevManager().setNullDev()
    if ep_config.global_options.enable_udp:
        log(None, "UDP transport enabled on port %d" % ep_config.port)
        sip_tp_config_udp = pj.TransportConfig()
        sip_tp_config_udp.port = ep_config.port
        _apply_transport_ip_config(sip_tp_config_udp, bind_ip=bind_ip, public_ip=bind_ip)
        try:
            end_point.transportCreate(pj.PJSIP_TRANSPORT_UDP, sip_tp_config_udp)
        except BaseException as e:
            raise RuntimeError(f"Failed to create UDP transport bound to {bind_ip or 'default'}:{ep_config.port}: {e}")
    if ep_config.global_options.enable_tcp:
        log(None, "TCP transport enabled on port %d" % ep_config.port)
        sip_tp_config_tcp = pj.TransportConfig()
        sip_tp_config_tcp.port = ep_config.port
        _apply_transport_ip_config(sip_tp_config_tcp, bind_ip=bind_ip, public_ip=bind_ip)
        try:
            end_point.transportCreate(pj.PJSIP_TRANSPORT_TCP, sip_tp_config_tcp)
        except BaseException as e:
            raise RuntimeError(f"Failed to create TCP transport bound to {bind_ip or 'default'}:{ep_config.port}: {e}")
    if ep_config.global_options.enable_tls:
        log(None, "TLS transport enabled on port %d" % ep_config.global_options.tls_port)
        sip_tp_config_tls = pj.TransportConfig()
        sip_tp_config_tls.port = ep_config.global_options.tls_port
        _apply_transport_ip_config(sip_tp_config_tls, bind_ip=bind_ip, public_ip=bind_ip)
        try:
            end_point.transportCreate(pj.PJSIP_TRANSPORT_TLS, sip_tp_config_tls)
        except BaseException as e:
            raise RuntimeError(f"Failed to create TLS transport bound to {bind_ip or 'default'}:{ep_config.global_options.tls_port}: {e}")
    end_point.libStart()
    return end_point
