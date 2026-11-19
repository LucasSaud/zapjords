import { useState, useRef, useEffect } from 'react';
import { API_URL, BARBERSHOP_MODE } from '../../../config';
import { useClient } from '../../../contexts/ClientContext';
import { toast } from 'react-hot-toast';
import { fetchWithAuth } from '../../../AuthContext';
import { appbarberFields, suggestAppbarberMapping } from '../appbarberMapping';

// Mapeamento de telefone pode ser:
// - uma string simples: nome da coluna com o telefone completo
// - um objeto { mode: 'composite', ddi_column, ddd_column, number_column, manual_ddi }:
//   quando o telefone está dividido em várias colunas (DDI/DDD/Número) na planilha.
// Retorna a mensagem de erro de validação, ou null se estiver válido.
export function getPhoneMappingError(phone) {
  if (!phone) return 'A coluna de Telefone é obrigatória.';
  if (typeof phone === 'object') {
    if (!phone.number_column) return 'Selecione a coluna do Número de telefone.';
    if (!phone.ddi_column && !phone.manual_ddi) {
      return 'Informe o DDI manualmente (ex: 55) ou selecione uma coluna de DDI.';
    }
  }
  return null;
}

export function useContactImport(onClose, onImportComplete) {
  const [importProfile, setImportProfile] = useState(BARBERSHOP_MODE ? 'appbarber' : 'generic');
  const [dateSemantics, setDateSemantics] = useState('appointment');
  const { activeClient } = useClient();
  const [step, setStep] = useState(1);
  const [file, setFile] = useState(null);
  const [loading, setLoading] = useState(false);
  const [previewData, setPreviewData] = useState(null);
  const [mapping, setMapping] = useState({
    name: '',
    phone: '',
    email: '',
    created_at: '',
    tags: '',
    remove_tags: ''
  });
  const [importResult, setImportResult] = useState(null);
  const fileInputRef = useRef(null);

  // Tags fixas digitadas manualmente no passo 2
  const [fixedTags, setFixedTags] = useState([]);
  const [fixedRemoveTags, setFixedRemoveTags] = useState([]);
  const [availableTags, setAvailableTags] = useState([]);

  useEffect(() => {
    const fetchAvailableTags = async () => {
      if (!activeClient?.id) return;
      try {
        const response = await fetchWithAuth(`${API_URL}/leads/filters`, {}, activeClient.id);
        if (response && response.ok) {
          const data = await response.json();
          if (Array.isArray(data.tags)) {
            setAvailableTags(data.tags);
          }
        }
      } catch (err) {
        console.error('Erro ao buscar etiquetas para importação:', err);
      }
    };
    fetchAvailableTags();
  }, [activeClient?.id]);

  const handleFileChange = async (e) => {
    const selectedFile = e.target.files[0];
    if (!selectedFile) return;

    const ext = selectedFile.name.split('.').pop().toLowerCase();
    if (!['csv', 'xlsx', 'xls'].includes(ext)) {
      toast.error('Formato não suportado. Use CSV ou Excel.');
      return;
    }

    setFile(selectedFile);
    setLoading(true);

    const formData = new FormData();
    formData.append('file', selectedFile);
    formData.append('import_profile', importProfile);

    try {
      const response = await fetch(`${API_URL}/leads/import/preview`, {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${localStorage.getItem('token')}`,
          'X-Client-ID': activeClient.id
        },
        body: formData
      });

      if (response.ok) {
        const data = await response.json();
        setPreviewData(data);

        // Auto-mapping suggestion
        const newMapping = { ...mapping };
        const lowerHeaders = data.headers.map(h => h.toLowerCase());
        
        const nameIdx = lowerHeaders.findIndex(h => h.includes('nome') || h.includes('name'));
        if (nameIdx !== -1) newMapping.name = data.headers[nameIdx];
        
        const phoneIdx = lowerHeaders.findIndex(h => h.includes('tel') || h.includes('phone') || h.includes('zap') || h.includes('cel'));
        if (phoneIdx !== -1) newMapping.phone = data.headers[phoneIdx];
        
        const emailIdx = lowerHeaders.findIndex(h => h.includes('email') || h.includes('mail'));
        if (emailIdx !== -1) newMapping.email = data.headers[emailIdx];

        const dateIdx = lowerHeaders.findIndex(h => !/últim|ultim|atendimento|agendamento|visita/.test(h) && (h.includes('data') || h.includes('date') || h.includes('chegada') || h.includes('criado') || h.includes('created') || h.includes('entrada') || h.includes('timestamp')));
        if (dateIdx !== -1) newMapping.created_at = data.headers[dateIdx];

        const tagsIdx = lowerHeaders.findIndex(h => (h.includes('tag') || h.includes('etiqueta')) && !h.includes('remove') && !h.includes('limp'));
        if (tagsIdx !== -1) newMapping.tags = data.headers[tagsIdx];

        const removeTagsIdx = lowerHeaders.findIndex(h => h.includes('remove') || h.includes('limp') || h.includes('exclui'));
        if (removeTagsIdx !== -1) newMapping.remove_tags = data.headers[removeTagsIdx];

        setMapping(importProfile === 'appbarber' ? suggestAppbarberMapping(data.headers) : newMapping);
        setStep(2);
      } else {
        let detail = 'Erro ao ler arquivo.';
        try { const errBody = await response.json(); detail = errBody.detail || detail; } catch (_) {}
        toast.error(detail);
      }
    } catch (err) {
      console.error(err);
      toast.error('Erro ao processar arquivo.');
    } finally {
      setLoading(false);
    }
  };

  const handleExecuteImport = async () => {
    if (importProfile === 'appbarber' && ['name', 'phone', ...appbarberFields.map(([key]) => key)].some(key => !mapping[key])) {
      toast.error('Mapeie os cinco campos da exportação AppBarber.');
      return;
    }
    const phoneError = getPhoneMappingError(mapping.phone);
    if (phoneError) {
      toast.error(phoneError);
      return;
    }

    // Validação preventiva: se alguma coluna selecionada estiver vazia em todas as linhas de prévia
    if (previewData && previewData.headers && previewData.preview_rows && previewData.preview_rows.length > 0) {
      const headers = previewData.headers;
      const rows = previewData.preview_rows;

      const isColEmpty = (colName) => {
        const idx = headers.indexOf(colName);
        if (idx === -1) return false;
        return rows.every(r => !r[idx] || String(r[idx]).trim() === '' || String(r[idx]).toLowerCase() === 'nan' || String(r[idx]).toLowerCase() === 'null');
      };

      // 1. Validar coluna de telefone
      if (typeof mapping.phone === 'string' && mapping.phone) {
        if (isColEmpty(mapping.phone)) {
          toast.error(`A coluna "${mapping.phone}" foi selecionada para Telefone, mas não possui nenhuma informação no arquivo.`);
          return;
        }
      } else if (typeof mapping.phone === 'object' && mapping.phone) {
        if (mapping.phone.number_column && isColEmpty(mapping.phone.number_column)) {
          toast.error(`A coluna "${mapping.phone.number_column}" selecionada para o Número não possui nenhuma informação no arquivo.`);
          return;
        }
      }

      // 2. Validar outras colunas mapeadas
      for (const [key, colName] of Object.entries(mapping)) {
        if (importProfile !== 'appbarber' && key !== 'phone' && typeof colName === 'string' && colName) {
          if (isColEmpty(colName)) {
            toast.error(`A coluna "${colName}" foi selecionada, mas não possui nenhuma informação no arquivo.`);
            return;
          }
        }
      }
    }

    setLoading(true);
    const formData = new FormData();
    formData.append('file', file);
    formData.append('mapping', JSON.stringify(mapping));
    formData.append('import_profile', importProfile);
    formData.append('date_semantics', dateSemantics);
    if (fixedTags.length > 0) formData.append('fixed_tags', fixedTags.join(','));
    if (fixedRemoveTags.length > 0) formData.append('fixed_remove_tags', fixedRemoveTags.join(','));

    try {
      const response = await fetch(`${API_URL}/leads/import/execute`, {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${localStorage.getItem('token')}`,
          'X-Client-ID': activeClient.id
        },
        body: formData
      });

      if (response.ok) {
        const result = await response.json();
        toast.success("Importação iniciada em segundo plano!");
        onClose();
        if (onImportComplete) {
          onImportComplete();
        }
        reset();
      } else {
        const error = await response.json();
        toast.error(error.detail || 'Erro na importação.');
      }
    } catch (err) {
      console.error(err);
      toast.error('Erro ao executar importação.');
    } finally {
      setLoading(false);
    }
  };


  const reset = () => {
    setStep(1);
    setFile(null);
    setPreviewData(null);
    setImportResult(null);
    setMapping({ name: '', phone: '', email: '', created_at: '', tags: '', remove_tags: '' });
    setFixedTags([]);
    setFixedRemoveTags([]);
    setImportProfile(BARBERSHOP_MODE ? 'appbarber' : 'generic');
    setDateSemantics('appointment');
  };

  return {
    importProfile, setImportProfile, dateSemantics, setDateSemantics,
    activeClient, step, setStep, file, setFile, loading, setLoading,
    previewData, setPreviewData, mapping, setMapping, importResult, setImportResult,
    fileInputRef,
    handleFileChange, handleExecuteImport, reset,
    fixedTags, setFixedTags, fixedRemoveTags, setFixedRemoveTags,
    availableTags
  };
}
