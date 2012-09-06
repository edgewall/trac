:mod:`trac.ticket.roadmap` -- The Roadmap and Milestone modules
===============================================================

.. module :: trac.ticket.roadmap

The `component` responsible for the *Roadmap* feature in Trac is the
`RoadmapModule`. It provides an overview of the milestones and the
progress in each of these milestones.

The `component` responsible for interacting with each milestone is the
`MilestoneModule`. A milestone also provides an overview of the
progress in terms of tickets processed.

The grouping of tickets in each progress bar is governed by the use of
another component implementing the `ITicketGroupStatsProvider`
interface. By default, this is the `DefaultTicketGroupStatsProvider`
(for both the `RoadmapModule` and the `MilestoneModule`), which
provides a configurable way to specify how tickets are grouped.


Interfaces
----------

.. autoclass :: ITicketGroupStatsProvider
   :members:

   See also :extensionpoints:`trac.ticket.roadmap.ITicketGroupStatsProvider`

.. autoclass :: TicketGroupStats
   :members:


Components
----------

.. autoclass :: MilestoneModule
   :members:
   :exclude-members: resource_exists

.. autoclass :: RoadmapModule
   :members:

.. autoclass :: DefaultTicketGroupStatsProvider
   :members:
   :exclude-members: milestone_groups_section


Helper Functions
----------------

.. autofunction :: apply_ticket_permissions
.. autofunction :: get_tickets_for_milestone
.. autofunction :: grouped_stats_data
