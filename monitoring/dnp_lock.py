"""Lock partage pour serialiser les acces a la DLL DNP Cx2Stat64.

La DLL DNP n'expose qu'un seul handle port a la fois : si le collector
heartbeat (printer.py, toutes les 60s) et le PrinterCounterWatcher
(printer_counter.py, toutes les 3s) font PortInitialize() en meme temps,
le second echoue -> l'agent interprete comme 'Imprimante deconnectee'
alors qu'elle marche.

Ce lock, importe par les 2, serialise leurs acces. Le tick le plus court
(3s) monopolise le port quelques millisecondes, le heartbeat attend
tranquillement son tour au lieu de conclure a une deconnexion.
"""

import threading

# RLock (re-entrant) : un meme thread peut prendre le lock plusieurs fois
# (necessaire car read_counter_and_status englobe open() + close() qui
# prennent aussi le lock chacun).
DNP_PORT_LOCK = threading.RLock()
