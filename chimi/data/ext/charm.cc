#include <Python.h>
#include <converse.h>

PyDoc_STRVAR(CmiNumCores_doc, "Get the number of cores on the local node.");

PY_CMI_NUM_CORES_CODE

static PyMethodDef
cmi_methods[] =
  {
    { "num_cores", (PyCFunction) PyCmiNumCores, METH_NOARGS, CmiNumCores_doc },
    {NULL, NULL, 0, NULL}
  };

extern "C"
PyMODINIT_FUNC
initcharm()
{
  PyObject* charm = Py_InitModule("charm", NULL);
  if ( charm )
    {
      PyObject* cmi = Py_InitModule("charm.cmi", cmi_methods);
      if ( cmi )
        PyModule_AddObject(charm, "cmi", cmi);
    }
}
