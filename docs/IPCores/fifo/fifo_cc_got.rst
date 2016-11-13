
fifo_cc_got
###########

This module implements a regular FIFO with common clock (cc), pipelined
interface. Common clock means read and write port use the same clock. The
FIFO size can be configured in word width (``D_BITS``) and minimum word count
``MIN_DEPTH``. The specified depth is rounded up to the next suitable value.

``DATA_REG`` (=true) is a hint, that distributed memory or registers should
be used as data storage. The actual memory type depends on the device
architecture. See implementation for details.

``*STATE_*_BITS`` defines the granularity of the fill state indicator
``*state_*``. If a fill state is not of interest, set ``*STATE_*_BITS = 0``.
``fstate_rd`` is associated with the read clock domain and outputs the
guaranteed number of words available in the FIFO. ``estate_wr`` is associated
with the write clock domain and outputs the number of words that is
guaranteed to be accepted by the FIFO without a capacity overflow. Note that
both these indicators cannot replace the ``full`` or ``valid`` outputs as
they may be implemented as giving pessimistic bounds that are minimally off
the true fill state.

``fstate_rd`` and ``estate_wr`` are combinatorial outputs and include an address
comparator (subtractor) in their path.

.. rubric:: Examples:

* FSTATE_RD_BITS = 1:

  +-----------+----------------------+
  | fstate_rd | filled (at least)    |
  +===========+======================+
  |    0      | 0/2 full             |
  +-----------+----------------------+
  |    1      | 1/2 full (half full) |
  +-----------+----------------------+

* FSTATE_RD_BITS = 2:

  +-----------+----------------------+
  | fstate_rd | filled (at least)    |
  +===========+======================+
  |    0      | 0/4 full             |
  +-----------+----------------------+
  |    1      | 1/4 full             |
  +-----------+----------------------+
  |    2      | 2/4 full (half full) |
  +-----------+----------------------+
  |    3      | 3/4 full             |
  +-----------+----------------------+



.. rubric:: Entity Declaration:

.. literalinclude:: ../../../src/fifo/fifo_cc_got.vhdl
   :language: vhdl
   :tab-width: 2
   :linenos:
   :lines: 98-124

Source file: `fifo/fifo_cc_got.vhdl <https://github.com/VLSI-EDA/PoC/blob/master/src/fifo/fifo_cc_got.vhdl>`_

.. seealso::

   :doc:`PoC.fifo.dc_got </PoC/fifo/fifo_dc_got>`
     For a FIFO with dependent clocks.
   :doc:`PoC.fifo.ic_got </PoC/fifo/fifo_ic_got>`
     For a FIFO with independent clocks (cross-clock FIFO).
   :doc:`PoC.fifo.glue </PoC/fifo/fifo_glue>`
     For a minimal FIFO / pipeline decoupling.


