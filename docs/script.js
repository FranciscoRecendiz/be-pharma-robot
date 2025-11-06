document.addEventListener('DOMContentLoaded', function() {
  // Ruta al archivo JSON (asegúrate de que esté en la carpeta correcta)
  const jsonFile = './reports/coverage_report_20251106_233615.json'; // Ajusta la ruta si es necesario
  
  // Usamos fetch para obtener el archivo JSON
  fetch(jsonFile)
    .then(response => {
      if (!response.ok) {
        throw new Error("No se pudo cargar el archivo JSON");
      }
      return response.json();
    })
    .then(data => {
      // Llamamos a la función para mostrar los datos
      displayReport(data);
    })
    .catch(error => {
      console.error("Error al cargar el archivo JSON:", error);
      document.getElementById('reporte').innerHTML = `<p>Error al cargar los datos.</p>`;
    });

  // Función para mostrar los datos en la página
  function displayReport(reportData) {
    const reportElement = document.getElementById('reporte');
    
    // 1. Análisis de saturación
    let saturationHTML = `
      <h2>1️⃣ ANÁLISIS DE SATURACIÓN</h2>
      <p><strong>Estado:</strong> ${reportData.saturation_analysis.is_saturated ? 'SATURADO ✅' : 'NO SATURADO ⚠️'}</p>
      <p><strong>Saturación estimada:</strong> ${reportData.saturation_analysis.saturation_pct}%</p>
      <p><strong>Productividad:</strong> ${reportData.saturation_analysis.productivity_ratio} empresas/combinación</p>
      <p><strong>Búsquedas vacías:</strong> ${reportData.saturation_analysis.empty_ratio * 100}%</p>
      <p><strong>Cache hits:</strong> ${reportData.saturation_analysis.cache_hit_ratio * 100}%</p>
      <p><strong>Duplicados:</strong> ${reportData.saturation_analysis.duplicate_ratio * 100}%</p>
      <h3>Recomendaciones:</h3>
      <div class="recommendation">
        <ul>`;
    reportData.saturation_analysis.recommendations.forEach(rec => {
      saturationHTML += `<li>${rec}</li>`;
    });
    saturationHTML += `</ul></div>`;

    // 2. Análisis de densidad geográfica
    let densityHTML = '<h2>2️⃣ ANÁLISIS DE DENSIDAD GEOGRÁFICA</h2>';
    densityHTML += `
      <table class="table table-bordered">
        <thead>
          <tr>
            <th>País</th>
            <th>Encontradas</th>
            <th>Esperadas</th>
            <th>Cobertura</th>
            <th>Status</th>
          </tr>
        </thead>
        <tbody>`;
    Object.keys(reportData.density_analysis).forEach(country => {
      const data = reportData.density_analysis[country];
      densityHTML += `
        <tr>
          <td>${country}</td>
          <td>${data.found}</td>
          <td>${data.expected}</td>
          <td>${data.coverage_pct}%</td>
          <td class="status ${getStatusClass(data.status)}">${data.status}</td>
        </tr>`;
    });
    densityHTML += `</tbody></table>`;

    // 3. Distribución por sector
    let sectorHTML = '<h2>3️⃣ DISTRIBUCIÓN POR SECTOR</h2>';
    sectorHTML += '<ul>';
    reportData.sector_distribution.forEach(sector => {
      sectorHTML += `<li>${sector.name}: ${sector.count} (${sector.percentage}%)</li>`;
    });
    sectorHTML += '</ul>';

    // 4. Análisis de exportadores
    let exportHTML = `<h2>4️⃣ ANÁLISIS DE EXPORTADORES</h2>`;
    exportHTML += `<p><strong>Empresas con evidencia de exportación:</strong> ${reportData.exporters.count}</p>`;
    exportHTML += '<ul>';
    reportData.exporters.top_exporters.forEach(exporter => {
      exportHTML += `<li>${exporter.name} (${exporter.country}) - ${exporter.confidence}%</li>`;
    });
    exportHTML += '</ul>';

    // 5. Gaps identificados
    let gapsHTML = '<h2>5️⃣ GAPS IDENTIFICADOS</h2>';
    gapsHTML += '<ul>';
    reportData.gaps.forEach(gap => {
      gapsHTML += `<li>${gap}</li>`;
    });
    gapsHTML += '</ul>';

    // 6. Recomendaciones de acción
    let recommendationsHTML = '<h2>6️⃣ RECOMENDACIONES DE ACCIÓN</h2>';
    recommendationsHTML += '<ul>';
    reportData.recommendations.forEach(rec => {
      recommendationsHTML += `<li>${rec}</li>`;
    });
    recommendationsHTML += '</ul>';

    // Insertamos todo el HTML generado
    reportElement.innerHTML = `
      ${saturationHTML}
      ${densityHTML}
      ${sectorHTML}
      ${exportHTML}
      ${gapsHTML}
      ${recommendationsHTML}`;
  }

  // Función para asignar clase de status
  function getStatusClass(status) {
    if (status === 'Excelente') return 'excellent';
    if (status === 'Bueno') return 'good';
    if (status === 'Mejorable') return 'improvable';
    return 'low';
  }
});
