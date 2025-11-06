document.addEventListener('DOMContentLoaded', function() {
  // Ruta al archivo JSON (asegurate de que esté en la carpeta correcta)
  const jsonFile = './reports/complementary_méxico_20251106.json'; // Cambia el nombre del archivo si es diferente
  
  // Usamos fetch para obtener el archivo JSON
  fetch(jsonFile)
    .then(response => {
      // Verificamos si la respuesta es correcta (status 200)
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

    // Título del reporte
    reportElement.innerHTML = `
      <h2>Reporte de Cobertura: ${reportData.country}</h2>
      <p><strong>Fecha del Reporte:</strong> ${new Date(reportData.timestamp).toLocaleString()}</p>
    `;
    
    // Mostrar eventos de trade shows
    if (reportData.trade_shows && reportData.trade_shows.length > 0) {
      let tradeShowHTML = '<h3>Eventos Relevantes</h3><div class="list-group">';
      reportData.trade_shows.forEach(event => {
        tradeShowHTML += `
          <div class="list-group-item">
            <h5><a href="${event.url}" target="_blank">${event.title}</a></h5>
            <p>${event.snippet}</p>
          </div>
        `;
      });
      tradeShowHTML += '</div>';
      reportElement.innerHTML += tradeShowHTML;
    } else {
      reportElement.innerHTML += '<p>No hay eventos de trade shows disponibles.</p>';
    }

    // Mostrar menciones de LinkedIn
    if (reportData.linkedin_mentions && reportData.linkedin_mentions.length > 0) {
      let linkedInHTML = '<h3>Menciones en LinkedIn</h3><ul>';
      reportData.linkedin_mentions.forEach(mention => {
        linkedInHTML += `<li>${mention}</li>`;
      });
      linkedInHTML += '</ul>';
      reportElement.innerHTML += linkedInHTML;
    } else {
      reportElement.innerHTML += '<p>No hay menciones de LinkedIn disponibles.</p>';
    }
  }
});
