#!/usr/bin/env python
# -*- Python -*-
# -*- coding: utf-8 -*-

'''rtshell

Copyright (C) 2009-2010
    Geoffrey Biggs
    RT-Synthesis Research Group
    Intelligent Systems Research Institute,
    National Institute of Advanced Industrial Science and Technology (AIST),
    Japan
    All rights reserved.
Licensed under the Eclipse Public License -v 1.0 (EPL)
http://www.opensource.org/licenses/eclipse-1.0.txt

rtcheck library.

'''


import optparse
import os
import os.path
import rtctree.path
import rtctree.tree
import rtsprofile.rts_profile
import sys

import rtshell
import rtshell.actions
import rtshell.rts_exceptions
import rtshell.options


class SystemNotOKCB(rtshell.actions.BaseCallback):
    '''Callback for a required action.

    Checks the action result and raises @ref RequiredActionFailedError if the
    action failed.

    '''
    def __init__(self, *args, **kwargs):
        super(SystemNotOKCB, self).__init__(*args, **kwargs)
        self._failed = False

    def __call__(self, result, err_msg):
        if err_msg:
            print >>sys.stderr, err_msg
        if not result:
            self._failed = True

    def __str__(self):
        return 'Required'

    @property
    def failed(self):
        '''Did any calls to this callback indicate failure?'''
        return self._failed


def get_data_conn_props(conn):
    return {'dataport.dataflow_type': str(conn.data_flow_type),
            'dataport.interface_type': str(conn.interface_type),
            'dataport.subscription_type': str(conn.subscription_type),
            'dataport.data_type': str(conn.data_type)}


def check_comps(rtsprofile, req_cb):
    checks = []
    for comp in [c for c in rtsprofile.components if c.is_required]:
        checks.append(rtshell.actions.CheckForRequiredCompAct(os.sep +
            comp.path_uri, comp.id, comp.instance_name, callbacks=[req_cb]))
    for comp in [c for c in rtsprofile.components if not c.is_required]:
        checks.append(rtshell.actions.CheckForRequiredCompAct(os.sep +
            comp.path_uri, comp.id, comp.instance_name))
    return checks


def check_connection(c, rtsprofile, props, cbs):
    s_comp = rtsprofile.find_comp_by_target(c.source_data_port)
    s_path = os.sep + s_comp.path_uri
    s_port = c.source_data_port.port_name
    prefix = s_comp.instance_name + '.'
    if s_port.startswith(prefix):
        s_port = s_port[len(prefix):]
    d_comp = rtsprofile.find_comp_by_target(c.target_data_port)
    d_path = os.sep + d_comp.path_uri
    d_port = c.target_data_port.port_name
    prefix = d_comp.instance_name + '.'
    if d_port.startswith(prefix):
        d_port = d_port[len(prefix):]
    return rtshell.actions.CheckForConnAct((s_path, s_port), (d_path, d_port),
            str(c.connector_id), props, callbacks=cbs)


def check_connections(rtsprofile, req_cb):
    checks = []
    for c in rtsprofile.required_data_connections():
        props = get_data_conn_props(c)
        checks.append(check_connection(c, rtsprofile, props, [req_cb]))

    for c in rtsprofile.optional_data_connections():
        props = get_data_conn_props(c)
        checks.append(check_connection(c, rtsprofile, props, []))

    for c in rtsprofile.required_service_connections():
        checks.append(check_connection(c, rtsprofile, {} [req_cb]))

    for c in rtsprofile.optional_service_connections():
        checks.append(check_connection(c, rtsprofile, {}, []))

    return checks


def check_configs(rtsprofile, req_cb):
    checks = []
    # Check the correct set is active
    for c in rtsprofile.components:
        if c.active_configuration_set:
            checks.append(rtshell.actions.CheckActiveConfigSetAct(os.sep +
                c.path_uri, c.active_configuration_set, callbacks=[req_cb]))
        for cs in c.configuration_sets:
            for p in cs.configuration_data:
                checks.append(rtshell.actions.CheckConfigParamAct(os.sep +
                    c.path_uri, cs.id, p.name, p.data, callbacks=[req_cb]))
    return checks


def check_states(rtsprofile, expected, req_cb):
    checks = []
    for comp in [c for c in rtsprofile.components if c.is_required]:
        for ec in comp.execution_contexts:
            checks.append(rtshell.actions.CheckCompStateAct(os.sep +
                comp.path_uri, comp.id, comp.instance_name, ec.id, expected,
                callbacks=[req_cb]))
    for comp in [c for c in rtsprofile.components if not c.is_required]:
        for ec in comp.execution_contexts:
            checks.append(rtshell.actions.CheckCompStateAct(os.sep +
                comp.path_uri, comp.id, comp.instance_name, ec.id, expected))
    return checks


def main(argv=None, tree=None):
    usage = '''Usage: %prog [options] <RTSProfile specification file>
Check that the running RT System conforms to an RTSProfile specification.

The input format will be determined automatically from the file extension.
If the file has no extension, the input format is assumed to be XML.
The output format can be over-ridden with the --xml or --yaml options.'''
    parser = optparse.OptionParser(usage=usage, version=rtshell.RTSH_VERSION)
    parser.add_option('--dry-run', dest='dry_run', action='store_true',
            default=False,
            help="Print what will be done but don't actually do anything. \
[Default: %default]")
    parser.add_option('-s', '--state', dest='state', action='store',
            type='string', default='Active',
            help='The expected state of the RT Components in the system. ' \
            '[Default: %default]')
    parser.add_option('-v', '--verbose', dest='verbose', action='store_true',
            default=False, help='Verbose output. [Default: %default]')
    parser.add_option('-x', '--xml', dest='xml', action='store_true',
            default=True, help='Use XML input format if no extension. \
[Default: %default]')
    parser.add_option('-y', '--yaml', dest='xml', action='store_false',
            help='Use YAML input format if no extension. \
[Default: %default]')

    if argv:
        sys.argv = [sys.argv[0]] + argv
    try:
        options, args = parser.parse_args()
    except optparse.OptionError, e:
        print >>sys.stderr, 'OptionError: ', e
        return 1
    rtshell.options.Options().verbose = options.verbose

    if not args:
        print >>sys.stderr, usage
        return 1

    # Load the profile
    ext = os.path.splitext(args[0])[1]
    if ext == '.xml':
        options.xml = True
    elif ext == '.yaml':
        options.xml = False
    with open(args[0]) as f:
        if options.xml:
            rtsp = rtsprofile.rts_profile.RtsProfile(xml_spec=f)
        else:
            rtsp = rtsprofile.rts_profile.RtsProfile(yaml_spec=f)
    # Build a list of actions to perform that will check the system
    cb = SystemNotOKCB()
    actions = check_comps(rtsp, cb) + \
            check_connections(rtsp, cb) + \
            check_configs(rtsp, cb) + \
            check_states(rtsp, options.state, cb)
    if options.dry_run:
        for a in actions:
            print a
    else:
        if not tree:
            # Load the RTC Tree, using the paths from the profile
            tree = rtctree.tree.create_rtctree(paths=[rtctree.path.parse_path(
                os.sep + c.path_uri)[0] for c in rtsp.components])
        try:
            for a in actions:
                a(tree)
        except rtshell.rts_exceptions.RtShellError, e:
            print >>sys.stderr, e
            return 1
    if cb.failed:
        return 1
    return 0


# vim: tw=79
